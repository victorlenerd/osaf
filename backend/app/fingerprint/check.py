"""Compare a new submission's fingerprint with every published review and decide.

duplicate: the same media: an exact hash, the same audio, or the same video with matching
           audio. The submission is rejected: it adds nothing and must never earn points.
similar:   close enough (audio above the similar line, or transcript text) that it publishes
           but earns no points; the closest review is recorded.
lookalike: video alone resembles another review. Someone filming two honest reviews in the
           same room produces near-identical frames, so this never blocks anything; it is only
           flagged for the person doing the monthly check.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.config import get_settings
from app.fingerprint import index
from app.fingerprint.score import audio_similarity, text_similarity, video_similarity
from app.models import Fingerprint, SimilarityMatch

log = logging.getLogger(__name__)


@dataclass
class Verdict:
    checked: bool  # False when the index could not be queried
    duplicate: SimilarityMatch | None = None
    similar: SimilarityMatch | None = None
    best: SimilarityMatch | None = None


def score(fp: Fingerprint, other: Fingerprint, review_id: str, business_id: str | None):
    return SimilarityMatch(
        review_id=review_id,
        business_id=business_id,
        exact=bool(fp.sha256 and fp.sha256 == other.sha256),
        audio=round(audio_similarity(fp.audio, other.audio), 3),
        video=round(video_similarity(fp.video, other.video), 3),
        text=round(text_similarity(fp.text, other.text), 3),
    )


def is_duplicate(m: SimilarityMatch) -> bool:
    s = get_settings()
    same_video = m.video >= s.dup_video_threshold and m.audio >= s.similar_audio_threshold
    return m.exact or m.audio >= s.dup_audio_threshold or same_video


def is_similar(m: SimilarityMatch) -> bool:
    s = get_settings()
    return m.audio >= s.similar_audio_threshold or m.text >= s.similar_text_threshold


def is_lookalike(m: SimilarityMatch) -> bool:
    return m.video >= get_settings().similar_video_threshold


def _rank(m: SimilarityMatch) -> float:
    return (2.0 if m.exact else 0.0) + max(m.audio, m.video, m.text)


def judge(matches: list[SimilarityMatch]) -> Verdict:
    v = Verdict(checked=True)
    if not matches:
        return v
    ordered = sorted(matches, key=_rank, reverse=True)
    v.best = ordered[0]
    v.duplicate = next((m for m in ordered if is_duplicate(m)), None)
    v.similar = v.duplicate or next((m for m in ordered if is_similar(m)), None)
    return v


def check(fp: Fingerprint, *, exclude: str | None = None) -> Verdict:
    """Never raises: a failing index yields an unchecked verdict, not a blocked review."""
    if not index.enabled():
        return Verdict(checked=False)
    try:
        docs = index.candidates(fp, exclude=exclude)
    except Exception:  # noqa: BLE001
        log.exception("fingerprint lookup failed")
        return Verdict(checked=False)
    matches = [
        score(fp, Fingerprint(**d.get("fp", {})), d["review_id"], d.get("business_id"))
        for d in docs
    ]
    return judge(matches)
