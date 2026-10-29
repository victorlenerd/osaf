"""Transcribe the reel audio with Meta Muse Voice Transcribe (diarized)."""

from __future__ import annotations

from pathlib import Path

from app.meta.client import get_meta
from app.models import Transcript

# Hints only: the model auto-detects; this biases towards languages common in our target markets.
DEFAULT_LANGUAGE_BIAS = ["English", "French", "Swahili", "Arabic", "Portuguese"]


def transcribe_audio(audio: Path, keywords: list[str] | None = None) -> tuple[Transcript, dict]:
    raw = get_meta().transcribe(audio, language_bias=DEFAULT_LANGUAGE_BIAS, keywords=keywords)
    return Transcript.from_asr(raw), raw
