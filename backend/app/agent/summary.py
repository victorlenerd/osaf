"""Running per-business summary (regenerated after every published review) and the on-demand
summary of a place's Google reviews."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from app.agent.prompts import GOOGLE_SUMMARY_SYSTEM, SUMMARY_SYSTEM
from app.config import get_settings
from app.meta.client import get_meta
from app.models import (
    Business,
    BusinessSummary,
    GooglePlaceDetails,
    GoogleReviewSummary,
    Review,
    now_iso,
)

log = logging.getLogger(__name__)

MAX_REVIEWS_IN_PROMPT = 50


def _strs(data: dict, key: str, n: int) -> list[str]:
    """Up to n short strings from a model-returned list, defensively."""
    return [str(x)[:120] for x in (data.get(key) or []) if isinstance(x, str | int | float)][:n]


def _review_view(r: Review) -> dict:
    e = r.extraction
    return {
        "review_id": r.review_id,
        "created_at": r.created_at,
        "recommend": e.recommend,
        "overall_sentiment": e.overall_sentiment,
        "good": e.good,
        "improve": e.improve,
        "keywords": e.keywords,
        "one_line_summary": e.one_line_summary,
        "language": e.language,
    }


def generate_summary(
    business: Business,
    reviews: list[Review],
    previous: BusinessSummary | None,
    *,
    chat: Callable[..., Any] | None = None,
) -> BusinessSummary:
    chat = chat or get_meta().chat
    reviews_sorted = sorted(reviews, key=lambda r: r.created_at, reverse=True)
    payload = {
        "business": {
            "name": business.name,
            "address": business.formatted_address,
            "category": business.category,
        },
        "previous_summary": previous.model_dump(
            include={"headline", "recurring_praise", "recurring_complaints", "standout_items"}
        )
        if previous
        else None,
        "reviews": [_review_view(r) for r in reviews_sorted[:MAX_REVIEWS_IN_PROMPT]],
    }
    messages = [
        {"role": "system", "content": SUMMARY_SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    data: dict = {}
    try:
        resp = chat(
            messages,
            response_format={"type": "json_object"},
            temperature=0.2,
            # Default reasoning overruns any sane max_tokens on this task (see the Google variant).
            max_tokens=1500,
            reasoning_effort="minimal",
        )
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001
        log.exception("summary generation failed; falling back to counts only")

    yes = sum(1 for r in reviews if r.extraction.recommend == "yes")
    total = len(reviews)
    sentiment = data.get("overall_sentiment")
    if sentiment not in ("positive", "mixed", "negative"):
        pos = sum(1 for r in reviews if r.extraction.overall_sentiment == "positive")
        neg = sum(1 for r in reviews if r.extraction.overall_sentiment == "negative")
        sentiment = "positive" if pos > neg else "negative" if neg > pos else "mixed"

    return BusinessSummary(
        overall_sentiment=sentiment,
        headline=str(
            data.get("headline")
            or (reviews_sorted[0].extraction.one_line_summary if reviews_sorted else "")
        )[:160],
        recurring_praise=_strs(data, "recurring_praise", 5),
        recurring_complaints=_strs(data, "recurring_complaints", 5),
        standout_items=_strs(data, "standout_items", 6),
        recommendation_rate=round(yes / total, 3) if total else 0.0,
        review_count=total,
        last_review_at=reviews_sorted[0].created_at if reviews_sorted else None,
        last_updated=now_iso(),
        model_version=get_settings().spark_model,
    )


# ------------------------------------------------------------------ Google reviews
def sentiment_from_rating(rating: float | None) -> str:
    if rating is None:
        return "mixed"
    return "positive" if rating >= 4.0 else "negative" if rating <= 2.5 else "mixed"


def summarize_google_reviews(
    place: GooglePlaceDetails,
    *,
    chat: Callable[..., Any] | None = None,
) -> GoogleReviewSummary:
    """Summarise the (max 5) Google reviews of a place. No LLM call when none has text."""
    settings = get_settings()
    textual = [r for r in place.reviews if r.text.strip()]
    base = GoogleReviewSummary(
        overall_sentiment=sentiment_from_rating(place.rating),  # type: ignore[arg-type]
        rating=place.rating,
        user_rating_count=place.user_rating_count,
        reviews_considered=len(textual),
        generated_at=now_iso(),
        model_version=settings.spark_model,
    )
    if not textual:
        return base

    chat = chat or get_meta().chat
    payload = {
        "business": {
            "name": place.name,
            "address": place.formatted_address,
            "primary_type": place.primary_type,
            "google_rating": place.rating,
            "google_rating_count": place.user_rating_count,
        },
        "reviews": [{"rating": r.rating, "text": r.text, "when": r.relative_time} for r in textual],
    }
    messages = [
        {"role": "system", "content": GOOGLE_SUMMARY_SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    data: dict = {}
    try:
        resp = chat(
            messages,
            response_format={"type": "json_object"},
            temperature=0.2,
            # Muse Spark's default reasoning burns ~5k tokens / 35 s on this task and overruns
            # any sane max_tokens; "minimal" answers in ~5 s with ~750 tokens.
            max_tokens=1500,
            reasoning_effort="minimal",
            timeout=settings.google_summary_timeout_seconds,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001
        log.exception("google summary failed for %s; falling back to rating only", place.place_id)
        return base

    sentiment = data.get("overall_sentiment")
    if sentiment in ("positive", "mixed", "negative"):
        base.overall_sentiment = sentiment
    base.headline = str(data.get("headline") or "")[:160]
    base.recurring_praise = _strs(data, "recurring_praise", 5)
    base.recurring_complaints = _strs(data, "recurring_complaints", 5)
    base.standout_items = _strs(data, "standout_items", 6)
    return base
