"""The review's own audio for the weekly reel: find it, pick a clip, decode it, measure it.

Sources, best first: the voice note's playable m4a, the reel's archived source video, then the
16 kHz WAV every submission keeps for transcription. A clip starts where the speech starts and
ends on a transcript turn boundary when one fits, so a reviewer is not cut mid-sentence unless a
single turn runs past the limit (then it fades out). Everything is decoded by ffmpeg to mono
48 kHz s16le, loudness-normalised so every review plays at the same level.
"""

from __future__ import annotations

import json
import logging
import math
import subprocess
from array import array
from dataclasses import dataclass
from pathlib import Path

from app.models import Transcript
from app.social.candidates import Candidate

log = logging.getLogger(__name__)

RATE = 48_000  # Instagram's maximum AAC sample rate
SAMPLE_BYTES = 2  # s16le mono
MIN_CLIP_MS = 3_000
LEAD_IN_MS = 200  # keep a breath before the first word
FADE_IN_S, FADE_OUT_S = 0.12, 0.45
AUDIO_EXTS = (".m4a", ".mp4", ".ogg", ".opus", ".wav", ".mp3", ".aac", ".aiff", ".mov", ".webm")


class ReviewAudioError(RuntimeError):
    pass


@dataclass
class ReviewAudio:
    review_id: str
    path: Path  # local source file (any ffmpeg input)
    duration_ms: int
    turns: list[tuple[int, int]]  # (start_ms, end_ms) of each transcript turn, may be empty


@dataclass
class Clip:
    review_id: str
    start_ms: int
    end_ms: int
    pcm: bytes  # mono s16le at RATE, already trimmed, faded and normalised

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


def turns_from_transcript(raw: dict | None) -> list[tuple[int, int]]:
    if not raw:
        return []
    t = Transcript.from_asr(raw)
    return [
        (x.start_ms, x.end_ms)
        for x in t.turns
        if x.start_ms is not None and x.end_ms is not None and x.end_ms > x.start_ms
    ]


def local_audio(c: Candidate, audio_dir: Path) -> ReviewAudio | None:
    """``<audio_dir>/<review_id>.<ext>``, with an optional ``<review_id>.transcript.json``
    (the raw ASR response) next to it. For samples and for re-renders without AWS."""
    for ext in AUDIO_EXTS:
        p = audio_dir / f"{c.review_id}{ext}"
        if p.exists():
            tj = audio_dir / f"{c.review_id}.transcript.json"
            raw = json.loads(tj.read_text()) if tj.exists() else None
            return ReviewAudio(c.review_id, p, probe_duration_ms(p), turns_from_transcript(raw))
    return None


def fetch_audio(c: Candidate, work: Path) -> ReviewAudio | None:
    """Download the review's audio (and transcript timings) from S3 into ``work``. Read-only."""
    from botocore.exceptions import ClientError

    from app.store import s3

    for key in s3_audio_keys(c):
        dest = work / f"{c.review_id}{Path(key).suffix or '.bin'}"
        try:
            s3.download_file(key, dest)
        except ClientError as e:
            log.info("no audio at %s: %s", key, e)
            continue
        raw = None
        if c.submission_id:
            try:
                raw = s3.get_json(s3.Keys.transcript_json(c.submission_id))
            except ClientError:
                raw = None
        return ReviewAudio(c.review_id, dest, probe_duration_ms(dest), turns_from_transcript(raw))
    return None


# ---------------------------------------------------------------------- the clip
def clip_window(duration_ms: int, turns: list[tuple[int, int]], max_ms: int) -> tuple[int, int]:
    """(start_ms, end_ms): from just before the first word, to the end of the last transcript
    turn that fits in ``max_ms``; a hard cut at ``max_ms`` when even the first turn is longer."""
    turns = sorted((max(0, s), min(e, duration_ms)) for s, e in turns if s < duration_ms)
    start = max(0, turns[0][0] - LEAD_IN_MS) if turns else 0
    limit = min(duration_ms, start + max_ms)
    fitting = [e for _, e in turns if e <= limit]
    end = max(fitting) if fitting else limit
    if end - start < MIN_CLIP_MS:  # the fitting turns are too short to stand alone
        end = limit
    return start, end


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


def make_clip(audio: ReviewAudio, *, max_s: float, normalise: bool = True) -> Clip:
    start, end = clip_window(audio.duration_ms, audio.turns, int(max_s * 1000))
    if end - start < 1000:
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
