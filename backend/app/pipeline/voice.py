"""WhatsApp voice notes: fetch, length-check, transcribe and prepare for playback on the site."""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.config import get_settings
from app.models import Transcript
from app.pipeline.download import extract_audio
from app.pipeline.transcribe import transcribe_audio
from app.whatsapp import client as wa


class VoiceNoteError(Exception):
    """The note cannot be used (too long, unreadable); the message is shown to the reviewer."""


def audio_duration(path: Path) -> float:
    """Container duration in seconds via ffprobe (works for audio-only files)."""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ]  # fmt: skip
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def fetch_voice_note(media_id: str, work: Path) -> Path:
    """Download the note from the WhatsApp media endpoint and enforce the ASR length limit."""
    work.mkdir(parents=True, exist_ok=True)
    ogg = wa.download_media(media_id, work / "voice.ogg")
    limit = get_settings().max_voice_note_seconds
    try:
        duration = audio_duration(ogg)
    except subprocess.CalledProcessError as e:
        raise VoiceNoteError("I couldn't read that voice note. Could you record it again?") from e
    if duration > limit:
        raise VoiceNoteError(
            f"That voice note is {duration / 60:.0f} minutes long; I can only listen to "
            f"{limit // 60} minutes. Could you send a shorter one?"
        )
    return ogg


def transcribe_voice_note(
    note: Path, work: Path, keywords: list[str] | None = None
) -> tuple[Transcript, dict]:
    """ogg/opus (or any ffmpeg input) -> mono WAV -> Muse Voice Transcribe."""
    wav = extract_audio(note, work / "audio.wav")
    return transcribe_audio(wav, keywords=keywords)


def transcode_for_playback(note: Path, out: Path) -> Path:
    """AAC in an MP4 container: plays everywhere, unlike WhatsApp's ogg/opus."""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(note),
        "-vn", "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", str(out),
    ]  # fmt: skip
    subprocess.run(cmd, check=True)
    return out
