"""Public read API consumed by the Next.js site."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.config import get_settings
from app.models import CATEGORIES, Review
from app.store import dynamo, opensearch, s3

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
