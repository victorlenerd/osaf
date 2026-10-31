"""Public read API consumed by the Next.js site."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.agent.places import get_place_details, search_places
from app.agent.summary import summarize_google_reviews
from app.config import get_settings
from app.models import CATEGORIES, Review
from app.store import dynamo, opensearch, s3

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["public"])


@router.get("/search")
def search(
    q: str = Query(default="", max_length=200),
    country: str | None = Query(default=None, max_length=2),
    category: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
):
    if category and category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="unknown category")
    return {"results": opensearch.search(q, country=country, category=category, limit=limit)}


@router.get("/categories")
def categories():
    return {"categories": CATEGORIES}


@router.get("/business/{business_id:path}")
def business(business_id: str):
    b = dynamo.get_business(business_id)
    if not b:
        raise HTTPException(status_code=404, detail="not found")
    summary = dynamo.get_summary(business_id)
    reviews = dynamo.list_reviews(business_id)
    loc = {"lat": b.lat, "lng": b.lng} if b.lat and b.lng else None
    return {
        "business": {
            "business_id": b.business_id,
            "source": b.source,
            "name": b.name,
            "formatted_address": b.formatted_address,
            "city": b.city or None,
            "country": b.country,
            "category": b.category,
            "google_primary_type": b.google_primary_type or None,
            "review_count": b.review_count,
            "recommend_rate": round(b.recommend_rate, 3),
            "recommend_counts": b.recommend_counts,
            "overall_sentiment": summary.overall_sentiment if summary else None,
            "summary_headline": summary.headline if summary else None,
            "keywords": [k for k, _ in sorted(b.keywords.items(), key=lambda kv: -kv[1])[:20]],
            "location": loc,
            "created_at": b.created_at,
            "updated_at": b.updated_at,
        },
        "summary": summary.model_dump() if summary else None,
        "reviews": [
            {
                "review_id": r.review_id,
                "created_at": r.created_at,
                "source": r.source,
                "reel_url": r.reel_url,
                "reel_shortcode": r.reel_shortcode,
                "audio_url": audio_url(r),
                "reviewer_display_name": r.reviewer_display_name,
                "extraction": r.extraction.model_dump(
                    exclude={"business", "confidence"}, exclude_none=True
                ),
            }
            for r in reviews
            if r.status == "published"
        ],
    }


def audio_url(r: Review) -> str | None:
    """Stable URL for a voice review's audio; the endpoint below redirects to a fresh S3 URL."""
    if r.source != "voice" or not r.audio_s3_key:
        return None
    base = get_settings().public_api_url.rstrip("/")
    return f"{base}/api/review/{r.review_id}/audio"


@router.get("/review/{review_id}/audio", status_code=302)
def review_audio(review_id: str):
    """Redirect to a short-lived S3 URL; the browser streams (and range-seeks) from S3 directly."""
    r = dynamo.get_review(review_id)
    if not r or r.status != "published" or not r.audio_s3_key:
        raise HTTPException(status_code=404, detail="no audio for this review")
    return RedirectResponse(s3.presigned_url(r.audio_s3_key, expires=3600), status_code=302)


# ------------------------------------------------------------ Google reviews on demand
GOOGLE_ATTRIBUTION = "Reviews from Google"


class _TokenBucket:
    """Per-process burst guard on paid Google calls.

    A daily quota set in Google Cloud console is the real cap."""

    def __init__(self, rate_per_minute: int):
        self.capacity = float(rate_per_minute)
        self.tokens = float(rate_per_minute)
        self.refill_per_s = rate_per_minute / 60.0
        self.updated = time.monotonic()
        self.lock = threading.Lock()

    def take(self) -> bool:
        with self.lock:
            now = time.monotonic()
            self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.refill_per_s)
            self.updated = now
            if self.tokens < 1:
                return False
            self.tokens -= 1
            return True


google_bucket = _TokenBucket(60)


def _google_call[T](fn: Callable[[], T]) -> T:
    """Run a Places call, mapping its failures to API errors (503 unconfigured, 502 upstream)."""
    if not google_bucket.take():
        raise HTTPException(status_code=429, detail="too many Google lookups, try again shortly")
    try:
        return fn()
    except RuntimeError as e:
        if "not configured" in str(e):
            raise HTTPException(status_code=503, detail="google lookup unavailable") from e
        log.warning("google places failed: %s", e)
        raise HTTPException(status_code=502, detail="google lookup failed") from e
    except Exception as e:  # noqa: BLE001  (httpx transport errors etc.)
        log.warning("google places failed: %r", e)
        raise HTTPException(status_code=502, detail="google lookup failed") from e


@router.get("/places/lookup")
def places_lookup(
    q: str = Query(min_length=2, max_length=200),
    country: str | None = Query(default=None, min_length=2, max_length=2),
    limit: int = Query(default=5, ge=1, le=5),
):
    """Verify a business name against Google Places. Used only when Afefehub search is empty."""
    cands = _google_call(lambda: search_places(q.strip(), country or "", max_results=limit))
    return {"candidates": [c.model_dump() for c in cands]}


@router.get("/places/{place_id}/google")
def place_google_reviews(place_id: str):
    """Live Google reviews (max 5, never stored) plus a cached (24 h) AI summary of them."""
    if place_id.startswith("afefe:") or not place_id.strip():
        raise HTTPException(status_code=404, detail="not a Google place")
    place = _google_call(lambda: get_place_details(place_id))
    if place is None:
        raise HTTPException(status_code=404, detail="not found")

    textual = sum(1 for r in place.reviews if r.text.strip())
    summary = dynamo.get_google_summary(place_id)
    if summary is None or summary.reviews_considered != textual:
        summary = summarize_google_reviews(place)
        if summary.reviews_considered and summary.headline:  # only cache LLM-generated text
            dynamo.put_google_summary(place_id, summary)
    return {
        "place": place.model_dump(exclude={"reviews"}),
        "summary": summary.model_dump(exclude={"expires_at"}),
        "reviews": [r.model_dump() for r in place.reviews],
        "attribution": GOOGLE_ATTRIBUTION,
    }
