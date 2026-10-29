"""Running per-business summary, regenerated after every published review."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from app.agent.prompts import SUMMARY_SYSTEM
from app.config import get_settings
from app.meta.client import get_meta
from app.models import Business, BusinessSummary, Review, now_iso

log = logging.getLogger(__name__)

MAX_REVIEWS_IN_PROMPT = 50


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
            max_tokens=800,
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

    def _strs(key: str, n: int) -> list[str]:
        return [str(x)[:120] for x in (data.get(key) or []) if isinstance(x, str | int | float)][:n]

    return BusinessSummary(
        overall_sentiment=sentiment,
        headline=str(
            data.get("headline")
            or (reviews_sorted[0].extraction.one_line_summary if reviews_sorted else "")
        )[:160],
        recurring_praise=_strs("recurring_praise", 5),
        recurring_complaints=_strs("recurring_complaints", 5),
        standout_items=_strs("standout_items", 6),
        recommendation_rate=round(yes / total, 3) if total else 0.0,
        review_count=total,
        last_review_at=reviews_sorted[0].created_at if reviews_sorted else None,
        last_updated=now_iso(),
        model_version=get_settings().spark_model,
    )
