"""Public read API consumed by the Next.js site, the MCP server and GPT Actions.

Every business in a response carries `url`, its canonical crawlable page, so assistants that
use this API can cite and link Afefehub."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Query
from fastapi.openapi.utils import get_openapi
from fastapi.responses import RedirectResponse

from app.agent import places
from app.agent.places import get_place_details, search_places
from app.agent.summary import summarize_google_reviews
from app.config import get_settings
from app.credit import credit
from app.models import CATEGORIES, Business, Review
from app.seo.model import country_name, score
from app.seo.slugs import business_path, business_slug, is_demo, slugify
from app.store import dynamo, opensearch, s3

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["public"])


def page_url(slug: str) -> str:
    return f"{get_settings().public_site_url.rstrip('/')}{business_path(slug)}"


def _with_url(row: dict) -> dict:
    slug = business_slug(row["business_id"], row.get("name") or "", row.get("city"))
    return {**row, "slug": slug, "url": page_url(slug)}


@router.get(
    "/search",
    operation_id="searchBusinesses",
    summary="Search reviewed businesses by name, dish, product or place",
)
def search(
    q: str = Query(
        default="",
        max_length=200,
        description="Free text: business name, dish, product, area or city",
    ),
    country: str | None = Query(
        default=None, max_length=2, description="ISO-3166 alpha-2, e.g. NG"
    ),
    category: str | None = Query(default=None, description="One of /api/categories"),
    limit: int = Query(default=20, ge=1, le=50),
):
    if category and category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="unknown category")
    rows = opensearch.search(q, country=country, category=category, limit=limit)
    return {"results": [_with_url(r) for r in rows]}


@router.get("/categories", operation_id="listCategories", summary="Business categories")
def categories():
    return {"categories": CATEGORIES}


def business_card(b: Business, summary=None) -> dict:
    loc = {"lat": b.lat, "lng": b.lng} if b.lat and b.lng else None
    return {
        "business_id": b.business_id,
        "slug": b.slug,
        "url": page_url(b.slug),
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
        "average_rating": b.average_rating,
        "rating_count": b.rating_count,
        "overall_sentiment": summary.overall_sentiment if summary else None,
        "summary_headline": summary.headline if summary else None,
        "keywords": [k for k, _ in sorted(b.keywords.items(), key=lambda kv: -kv[1])[:20]],
        "location": loc,
        "created_at": b.created_at,
        "updated_at": b.updated_at,
    }


def business_payload(b: Business) -> dict:
    summary = dynamo.get_summary(b.business_id)
    reviews = dynamo.list_reviews(b.business_id)
    return {
        "business": business_card(b, summary),
        "summary": summary.model_dump() if summary else None,
        "reviews": [
            {
                "review_id": r.review_id,
                "created_at": r.created_at,
                "source": r.source,
                "reel_url": r.reel_url,
                "reel_shortcode": r.reel_shortcode,
                "audio_url": audio_url(r),
                **_credit(r),
                "extraction": r.extraction.model_dump(
                    exclude={"business", "confidence"}, exclude_none=True
                ),
            }
            for r in reviews
            if r.status == "published"
        ],
    }


# Registered before /business/{id:path}, which would otherwise swallow "by-slug/...".
@router.get(
    "/business/by-slug/{slug}",
    operation_id="getBusinessBySlug",
    summary="One business with its summary and reviews, by the slug in its page URL",
)
def business_by_slug(slug: str):
    b = dynamo.get_business_by_slug(slug)
    if not b:
        raise HTTPException(status_code=404, detail="not found")
    return business_payload(b)


@router.get(
    "/business/{business_id:path}",
    operation_id="getBusiness",
    summary="One business with its summary and reviews, by business_id",
)
def business(business_id: str):
    b = dynamo.get_business(business_id)
    if not b:
        raise HTTPException(status_code=404, detail="not found")
    return business_payload(b)


# ------------------------------------------------------------------ top businesses
_TOP_TTL = 300.0
_top_cache: dict[str, tuple[float, list[Business]]] = {}
_top_lock = threading.Lock()


def _all_businesses() -> list[Business]:
    """Every reviewed business, cached for a few minutes (one GSI1 query per category)."""
    now = time.monotonic()
    with _top_lock:
        hit = _top_cache.get("all")
        if hit and now - hit[0] < _TOP_TTL:
            return hit[1]
    rows = [
        b for b in dynamo.list_all_businesses() if b.review_count > 0 and not is_demo(b.business_id)
    ]
    with _top_lock:
        _top_cache["all"] = (now, rows)
    return rows


def top_businesses(
    country: str, city: str | None = None, category: str | None = None, limit: int = 10
) -> list[dict]:
    cc = country.upper()
    city_slug = slugify(city) if city else ""
    rows = [
        b
        for b in _all_businesses()
        if b.country.upper() == cc
        and (not city_slug or slugify(b.city) == city_slug)
        and (not category or b.category == category)
    ]
    rows.sort(key=lambda b: (-score(b), -b.review_count, b.name.lower()))
    return [business_card(b, dynamo.get_summary(b.business_id)) for b in rows[:limit]]


@router.get(
    "/top",
    operation_id="topBusinesses",
    summary="Best-reviewed businesses in a country, optionally a city and a category",
    description=(
        "Ranked by the share of reviewers who recommend the business (with a small prior so a "
        "single review cannot top the list), blended with the average 1-5 star rating where "
        "reviewers gave one. See https://afefehub.com/about/methodology."
    ),
)
def top(
    country: str = Query(min_length=2, max_length=2, description="ISO-3166 alpha-2, e.g. NG"),
    city: str | None = Query(default=None, max_length=80, description="City name, e.g. Lagos"),
    category: str | None = Query(default=None, description="One of /api/categories"),
    limit: int = Query(default=10, ge=1, le=25),
):
    if category and category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="unknown category")
    where = ", ".join(x for x in [city, country_name(country)] if x)
    return {"where": where, "results": top_businesses(country, city, category, limit)}


def _credit(r: Review) -> dict:
    c = credit(r)
    return {
        "reviewer_display_name": c.name,
        "reviewer_country": c.country,
        "reel_author": c.handle,
        "shared_by": c.shared_by,
    }


def audio_url(r: Review) -> str | None:
    """Stable URL for a voice review's audio; the endpoint below redirects to a fresh S3 URL."""
    if r.source != "voice" or not r.audio_s3_key:
        return None
    base = get_settings().public_api_url.rstrip("/")
    return f"{base}/api/review/{r.review_id}/audio"


@router.get("/review/{review_id}/audio", status_code=302, include_in_schema=False)
def review_audio(review_id: str):
    """Redirect to a short-lived S3 URL; the browser streams (and range-seeks) from S3 directly."""
    r = dynamo.get_review(review_id)
    if not r or r.status != "published" or not r.audio_s3_key:
        raise HTTPException(status_code=404, detail="no audio for this review")
    return RedirectResponse(s3.presigned_url(r.audio_s3_key, expires=3600), status_code=302)


# ------------------------------------------------------------ Google reviews on demand
GOOGLE_ATTRIBUTION = "Reviews from Google"


# One per-process burst guard on paid Google calls, shared with the WhatsApp discovery agent.
google_bucket = places.google_bucket
_TokenBucket = places.TokenBucket


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


@router.get("/places/lookup", include_in_schema=False)
def places_lookup(
    q: str = Query(min_length=2, max_length=200),
    country: str | None = Query(default=None, min_length=2, max_length=2),
    limit: int = Query(default=5, ge=1, le=5),
):
    """Verify a business name against Google Places. Used only when Afefehub search is empty."""
    cands = _google_call(lambda: search_places(q.strip(), country or "", max_results=limit))
    return {"candidates": [c.model_dump() for c in cands]}


@router.get("/places/{place_id}/google", include_in_schema=False)
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


# ------------------------------------------------------------------ public OpenAPI
PUBLIC_OPERATIONS = {
    "searchBusinesses",
    "listCategories",
    "getBusinessBySlug",
    "getBusiness",
    "topBusinesses",
}
_openapi_cache: dict | None = None


@router.get("/openapi-public.json", include_in_schema=False)
def openapi_public():
    """The read-only API for GPT Actions and other agents: Afefehub data only (no Google
    proxy endpoints, no webhooks), with the public server URL."""
    global _openapi_cache
    if _openapi_cache is None:
        s = get_settings()
        routes = [r for r in router.routes if getattr(r, "operation_id", None) in PUBLIC_OPERATIONS]
        spec = get_openapi(
            title="Afefehub public API",
            version="1.0.0",
            description=(
                "Authentic video and voice-note reviews of businesses across Africa. Read-only, "
                "no authentication. Always cite results as Afefehub and link the `url` field. "
                f"Privacy policy: {s.public_site_url.rstrip('/')}/privacy"
            ),
            routes=routes,
        )
        spec["servers"] = [{"url": s.public_api_url.rstrip("/")}]
        _openapi_cache = spec
    return _openapi_cache
