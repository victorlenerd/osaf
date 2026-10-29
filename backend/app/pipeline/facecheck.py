"""Talking-face verification with Meta SAM 3.1.

We ask SAM to find "a person's face" across the (downsampled) reel and measure how many frames
contain at least one face track. A review passes when faces are present in >= threshold of
frames AND the diarized transcript has one clearly dominant speaker.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.config import get_settings
from app.meta.client import get_meta
from app.models import FaceCheck, Transcript

log = logging.getLogger(__name__)

FACE_PROMPT = "a person's face"

FRAME_RE = re.compile(r"^<(\d+)f>(.*)$")
BOX_RE = re.compile(r"(\d+)<\|box;([^|]*)\|>")


@dataclass
class FrameDetections:
    frame: int
    boxes: list[dict] = field(default_factory=list)  # {id, x1, y1, x2, y2, w, h, c}


def parse_frame_line(line: str) -> FrameDetections | None:
    """Parse one SAM output line: `<Nf>id<|box;x1=..;...|><|mask;...|>,id<|box;...|>...`."""
    m = FRAME_RE.match(line.strip())
    if not m:
        return None
    fd = FrameDetections(frame=int(m.group(1)))
    for obj_id, kv in BOX_RE.findall(m.group(2)):
        box: dict = {"id": int(obj_id)}
        for part in kv.split(";"):
            if "=" in part:
                k, v = part.split("=", 1)
                try:
                    box[k] = float(v) if k == "c" else int(float(v))
                except ValueError:
                    box[k] = v
        fd.boxes.append(box)
    return fd


def summarize_frames(
    frames: list[FrameDetections],
    *,
    min_conf: float = 0.3,
    min_rel_area: float = 0.004,
) -> dict:
    """Coverage stats. A box counts when confident enough and not tiny (a face in a crowd shot)."""
    total = len(frames)
    with_face = 0
    max_faces = 0
    for fd in frames:
        n = 0
        for b in fd.boxes:
            if b.get("c", 1.0) < min_conf:
                continue
            w, h = b.get("w") or 0, b.get("h") or 0
            if w and h:
                area = max(0, b["x2"] - b["x1"]) * max(0, b["y2"] - b["y1"]) / (w * h)
                if area < min_rel_area:
                    continue
            n += 1
        if n:
            with_face += 1
        max_faces = max(max_faces, n)
    return {
        "frames_total": total,
        "frames_with_face": with_face,
        "coverage": (with_face / total) if total else 0.0,
        "max_concurrent_faces": max_faces,
    }


def run_face_check(video_url: str, transcript: Transcript | None) -> tuple[FaceCheck, dict]:
    """Call SAM on a presigned/public MP4 URL and decide. Returns (result, raw_artifact)."""
    s = get_settings()
    frames: list[FrameDetections] = []
    raw_lines: list[str] = []
    for line in get_meta().sam_video_lines(video_url, FACE_PROMPT):
        raw_lines.append(line)
        fd = parse_frame_line(line)
        if fd:
            frames.append(fd)
    stats = summarize_frames(frames)
    speaker_share = transcript.dominant_speaker_share() if transcript else 1.0

    reasons = []
    if stats["coverage"] < s.face_coverage_threshold:
        reasons.append(
            f"a face is visible in only {stats['coverage']:.0%} of the video "
            f"(need {s.face_coverage_threshold:.0%})"
        )
    if speaker_share < s.dominant_speaker_threshold:
        reasons.append(f"no single dominant speaker ({speaker_share:.0%})")
    passed = not reasons
    result = FaceCheck(
        passed=passed,
        face_frame_coverage=round(stats["coverage"], 3),
        frames_total=stats["frames_total"],
        frames_with_face=stats["frames_with_face"],
        max_concurrent_faces=stats["max_concurrent_faces"],
        dominant_speaker_share=round(speaker_share, 3),
        reason="ok" if passed else "; ".join(reasons),
    )
    artifact = {
        "prompt": FACE_PROMPT,
        "model": s.sam_model,
        "stats": stats,
        "frames": [{"frame": f.frame, "boxes": f.boxes} for f in frames],
        "raw_line_count": len(raw_lines),
    }
    return result, artifact
