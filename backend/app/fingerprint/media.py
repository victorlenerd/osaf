"""Fingerprints computed from local media files. Every function degrades to "nothing" (an
empty list or None) rather than raising, so a missing tool never blocks a review; the
submission is then flagged as not fully checked."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

AUDIO_SECONDS = 180  # Chromaprint over the first 3 minutes is plenty to recognise a copy
VIDEO_FPS = 1
VIDEO_MAX_FRAMES = 180
_FRAME_W, _FRAME_H = 9, 8  # dHash: 9x8 grey pixels -> 8 comparisons per row -> 64 bits


def sha256_file(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        log.warning("could not hash %s", path.name)
        return None


def audio_fingerprint(path: Path, seconds: int = AUDIO_SECONDS) -> list[int]:
    """Chromaprint raw fingerprint (about 8 uint32 values per second) via `fpcalc`."""
    if not shutil.which("fpcalc"):
        log.warning("fpcalc not installed; skipping audio fingerprint")
        return []
    try:
        out = subprocess.run(
            ["fpcalc", "-raw", "-json", "-length", str(seconds), str(path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        ).stdout
        values = json.loads(out).get("fingerprint") or []
        return [int(v) & 0xFFFFFFFF for v in values]
    except (subprocess.SubprocessError, ValueError, OSError) as e:
        log.warning("audio fingerprint failed: %s", str(e)[:200])
        return []


def dhash_frames(raw: bytes) -> list[int]:
    """64-bit difference hash for each 9x8 grey frame in a raw byte stream."""
    size = _FRAME_W * _FRAME_H
    hashes = []
    for off in range(0, len(raw) - size + 1, size):
        px = raw[off : off + size]
        bits = 0
        for row in range(_FRAME_H):
            base = row * _FRAME_W
            for col in range(_FRAME_W - 1):
                bits = (bits << 1) | (px[base + col] > px[base + col + 1])
        hashes.append(bits)
    return hashes


def video_fingerprint(
    path: Path, fps: int = VIDEO_FPS, max_frames: int = VIDEO_MAX_FRAMES
) -> list[int]:
    """One dHash per second of video, from ffmpeg-scaled 9x8 grey frames."""
    cmd = [
        "ffmpeg", "-v", "error", "-i", str(path), "-an",
        "-vf", f"fps={fps},scale={_FRAME_W}:{_FRAME_H}:flags=area,format=gray",
        "-frames:v", str(max_frames), "-f", "rawvideo", "-",
    ]  # fmt: skip
    try:
        raw = subprocess.run(cmd, check=True, capture_output=True, timeout=300).stdout
    except (subprocess.SubprocessError, OSError) as e:
        log.warning("video fingerprint failed: %s", str(e)[:200])
        return []
    return dhash_frames(raw)
