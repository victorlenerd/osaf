"""The review's own audio for its single-review Reel: find it, decode it, measure it.

Sources, best first: the voice note's playable m4a, the reel's archived source video, then the
16 kHz WAV every submission keeps for transcription. The Reel plays the whole recording; ffmpeg
only evens out the loudness and adds a few-millisecond fade at each end so it starts and stops
without a click. Anything longer than ``MAX_SECONDS`` (Instagram allows 15 min) is cut there.
Decoded to mono 48 kHz s16le.
"""

from __future__ import annotations

import logging
import math
import subprocess
from array import array
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from app.social.candidates import Candidate

log = logging.getLogger(__name__)

RATE = 48_000  # Instagram's maximum AAC sample rate
SAMPLE_BYTES = 2  # s16le mono
MIN_CLIP_MS = 1_000
MAX_SECONDS = 870.0  # 14:30, so the closing card still fits under Instagram's 15 min
FADE_IN_S, FADE_OUT_S = 0.03, 0.3
AUDIO_EXTS = (".m4a", ".mp4", ".ogg", ".opus", ".wav", ".mp3", ".aac", ".aiff", ".mov", ".webm")


class ReviewAudioError(RuntimeError):
    pass


@dataclass
class ReviewAudio:
    review_id: str
    path: Path  # local source file (any ffmpeg input)
    duration_ms: int


@dataclass
class Clip:
    review_id: str
    start_ms: int
    end_ms: int
    pcm: bytes  # mono s16le at RATE, normalised, with click-free ends

    @property
    def duration_s(self) -> float:
        return len(self.pcm) / (RATE * SAMPLE_BYTES)


# ---------------------------------------------------------------------- finding
def s3_audio_keys(c: Candidate) -> list[str]:
    """S3 keys that may hold this review's audio, best first."""
    from app.store.s3 import Keys

    keys = [c.audio_s3_key, c.video_s3_key]
    if c.submission_id:
        keys += [Keys.audio(c.submission_id), Keys.voice_source(c.submission_id)]
    return [k for k in dict.fromkeys(keys) if k]


def probe_duration_ms(path: Path) -> int:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    try:
        return int(float(out.stdout.strip()) * 1000)
    except ValueError as e:
        raise ReviewAudioError(f"ffprobe could not read {path.name}: {out.stderr.strip()}") from e


def s3_sources(c: Candidate, work: Path) -> Iterator[Path]:
    """Download each S3 key that may hold the review's audio into ``work``, best first, lazily:
    the caller stops pulling as soon as one decodes. Missing keys are skipped. Read-only."""
    from botocore.exceptions import ClientError

    from app.store import s3

    for key in s3_audio_keys(c):
        dest = work / f"{c.review_id}{Path(key).suffix or '.bin'}"
        try:
            s3.download_file(key, dest)
        except ClientError as e:
            log.info("no audio at %s: %s", key, e)
            continue
        yield dest


def local_sources(c: Candidate, audio_dir: Path) -> Iterator[Path]:
    """``<audio_dir>/<review_id>.<ext>`` files, in AUDIO_EXTS order."""
    for ext in AUDIO_EXTS:
        p = audio_dir / f"{c.review_id}{ext}"
        if p.exists():
            yield p


def first_clip(
    review_id: str, sources: Iterable[Path], *, max_s: float = MAX_SECONDS
) -> tuple[ReviewAudio, Clip]:
    """The first source that probes and decodes, as (audio, clip). A file that downloads but
    cannot be read (corrupt, or a video with no audio track) falls through to the next one.
    Raises ReviewAudioError naming why each source failed, or that there were none."""
    errors: list[str] = []
    for path in sources:
        try:
            audio = ReviewAudio(review_id, path, probe_duration_ms(path))
            return audio, make_clip(audio, max_s=max_s)
        except ReviewAudioError as e:
            log.info("audio source %s unusable: %s", path.name, e)
            errors.append(f"{path.name}: {e}")
    if not errors:
        raise ReviewAudioError("no audio found")
    raise ReviewAudioError("no usable audio (" + "; ".join(errors) + ")")


# ---------------------------------------------------------------------- decoding
def decode_clip(src: Path, start_ms: int, end_ms: int, *, normalise: bool = True) -> bytes:
    dur = max(0.0, (end_ms - start_ms) / 1000)
    filters = []
    if normalise:
        filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")
    filters += [
        f"afade=t=in:st=0:d={FADE_IN_S}",
        f"afade=t=out:st={max(0.0, dur - FADE_OUT_S):.3f}:d={FADE_OUT_S}",
    ]
    cmd = [
        "ffmpeg", "-v", "error", "-ss", f"{start_ms / 1000:.3f}", "-t", f"{dur:.3f}",
        "-i", str(src), "-vn", "-af", ",".join(filters),
        "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-",
    ]  # fmt: skip
    out = subprocess.run(cmd, capture_output=True, check=False)
    if out.returncode != 0 or not out.stdout:
        raise ReviewAudioError(f"ffmpeg could not decode {src.name}: {out.stderr.decode()[-300:]}")
    pcm = out.stdout
    want = int(dur * RATE) * SAMPLE_BYTES
    return pcm[:want] if len(pcm) > want else pcm  # loudnorm can pad a few ms


def make_clip(audio: ReviewAudio, *, max_s: float = MAX_SECONDS, normalise: bool = True) -> Clip:
    """The whole recording, cut at ``max_s`` only if it runs longer."""
    start, end = 0, min(audio.duration_ms, int(max_s * 1000))
    if end - start < MIN_CLIP_MS:
        raise ReviewAudioError(f"{audio.review_id}: audio is too short ({end - start} ms)")
    pcm = decode_clip(audio.path, start, end, normalise=normalise)
    return Clip(audio.review_id, start, end, pcm)


# ---------------------------------------------------------------------- the waveform
def peaks(pcm: bytes, bars: int, *, gamma: float = 0.8) -> list[float]:
    """One value in [0, 1] per bar: the slice's RMS loudness, scaled to the clip's loudest slice
    and compressed by ``gamma`` so quiet speech still reads as speech. RMS rather than the peak
    sample, because normalised speech peaks near full scale almost everywhere."""
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % SAMPLE_BYTES])
    n = len(samples)
    if not n or bars <= 0:
        return [0.0] * max(0, bars)
    raw: list[float] = []
    for i in range(bars):
        a, b = n * i // bars, max(n * (i + 1) // bars, n * i // bars + 1)
        chunk = samples[a:b]
        raw.append(math.sqrt(math.sumprod(chunk, chunk) / len(chunk)) if chunk else 0.0)
    top = max(raw) or 1.0
    return [(v / top) ** gamma for v in raw]


def silence(seconds: float) -> bytes:
    return bytes(int(seconds * RATE) * SAMPLE_BYTES)
