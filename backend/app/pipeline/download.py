"""Fetch a public Instagram reel and prepare the audio track for Muse Voice Transcribe."""

from __future__ import annotations

import base64
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yt_dlp

from app.config import get_settings

log = logging.getLogger(__name__)

IG_URL_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?:[A-Za-z0-9_.]+/)?(reel|reels|p|tv)/([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)


class DownloadError(Exception):
    """Raised when the reel cannot be fetched (private, deleted, rate-limited, bad link)."""

    def __init__(self, message: str, *, retryable_via_whatsapp: bool = True):
        super().__init__(message)
        self.retryable_via_whatsapp = retryable_via_whatsapp


def extract_reel(text: str) -> tuple[str, str] | None:
    """Return (canonical_url, shortcode) for the first Instagram reel/post link in text."""
    m = IG_URL_RE.search(text or "")
    if not m:
        return None
    shortcode = m.group(2)
    return f"https://www.instagram.com/reel/{shortcode}/", shortcode


@dataclass
class DownloadResult:
    video_path: Path
    audio_path: Path
    duration_s: float | None
    title: str | None
    uploader: str | None


def _cookie_file(work: Path) -> Path | None:
    b64 = get_settings().ig_cookies_b64
    if not b64:
        return None
    p = work / "cookies.txt"
    p.write_bytes(base64.b64decode(b64))
    return p


def download_reel(url: str, work: Path) -> DownloadResult:
    work.mkdir(parents=True, exist_ok=True)
    out = work / "source.%(ext)s"
    opts = {
        "outtmpl": str(out),
        "format": "bv*[ext=mp4][vcodec^=avc1]+ba[ext=m4a]/b[ext=mp4]/b",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "retries": 2,
    }
    cookies = _cookie_file(work)
    if cookies:
        opts["cookiefile"] = str(cookies)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as e:  # noqa: PERF203
        msg = str(e)
        low = msg.lower()
        if "login" in low or "private" in low or "not available" in low or "404" in low:
            raise DownloadError(
                "That reel looks private or unavailable. Make sure the account and reel are public."
            ) from e
        if "rate" in low or "429" in low or "blocked" in low:
            raise DownloadError("Instagram is rate-limiting downloads right now.") from e
        raise DownloadError(f"Could not download the reel: {msg[:200]}") from e

    video = work / "source.mp4"
    if not video.exists():
        candidates = sorted(work.glob("source.*"))
        if not candidates:
            raise DownloadError("Download produced no file.")
        video = candidates[0]
    audio = extract_audio(video, work / "audio.wav")
    return DownloadResult(
        video_path=video,
        audio_path=audio,
        duration_s=(info or {}).get("duration"),
        title=(info or {}).get("title"),
        uploader=(info or {}).get("uploader"),
    )


def extract_audio(video: Path, audio: Path, sample_rate: int = 24000) -> Path:
    """Mono 16-bit PCM WAV, the only format Muse Voice Transcribe's file endpoint accepts."""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
        "-vn", "-ac", "1", "-ar", str(sample_rate), "-c:a", "pcm_s16le", "-map_metadata", "-1",
        str(audio),
    ]  # fmt: skip
    subprocess.run(cmd, check=True)
    return audio


def probe(video: Path) -> dict:
    """Return {duration, fps, width, height, nb_frames} via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,nb_frames,duration",
        "-of", "default=noprint_wrappers=1", str(video),
    ]  # fmt: skip
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    kv = dict(line.split("=", 1) for line in out.strip().splitlines() if "=" in line)
    num, _, den = (kv.get("r_frame_rate") or "30/1").partition("/")
    fps = float(num) / float(den or 1)
    duration = float(kv.get("duration") or 0)
    nb = kv.get("nb_frames")
    frames = int(nb) if nb and nb.isdigit() else int(duration * fps)
    return {
        "duration": duration,
        "fps": fps,
        "width": int(kv.get("width") or 0),
        "height": int(kv.get("height") or 0),
        "nb_frames": frames,
    }


def transcode_for_sam(video: Path, out: Path, max_frames: int = 1500, max_side: int = 720) -> Path:
    """Re-encode to H.264 MP4 at a reduced frame rate so SAM 3.1 processes ~2 fps of a reel.

    SAM bills per frame (min 50); a 60 s reel at 2 fps is 120 frames, plenty to detect a face.
    """
    info = probe(video)
    duration = max(info["duration"], 1.0)
    target_fps = min(2.0, max(max_frames / duration, 50.0 / duration))
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
        "-an", "-r", f"{target_fps:.3f}",
        "-vf", f"scale='if(gt(iw,ih),{max_side},-2)':'if(gt(iw,ih),-2,{max_side})'",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(out),
    ]  # fmt: skip
    subprocess.run(cmd, check=True)
    return out
