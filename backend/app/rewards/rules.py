"""The payout rules in one place: points per kind, category groups and pools, windows, and
which published reviews may be entered at all."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.models import EntryKind, Review

LAGOS = ZoneInfo("Africa/Lagos")

GROUPS = ("shortlets", "restaurants", "hotels", "others")
GROUP_LABELS = {
    "shortlets": "Shortlets",
    "restaurants": "Restaurants",
    "hotels": "Hotels",
    "others": "Others",
}
CATEGORY_GROUP = {
    "shortlet": "shortlets",
    "restaurant": "restaurants",
    "street_food": "restaurants",
    "cafe": "restaurants",
    "hotel": "hotels",
}


def group_for(category: str) -> str:
    return CATEGORY_GROUP.get(category, "others")


def pools_ngn() -> dict[str, int]:
    s = get_settings()
    return {
        "shortlets": s.pool_shortlets_ngn,
        "restaurants": s.pool_restaurants_ngn,
        "hotels": s.pool_hotels_ngn,
        "others": s.pool_others_ngn,
    }


def points_for(kind: EntryKind) -> int:
    s = get_settings()
    return {"voice": s.points_voice, "reel_unverified": 0, "reel_author": s.points_reel_author}[
        kind
    ]


def window_for(when: datetime | None = None) -> str:
    """The payout window (calendar month in Lagos time) a review entered now belongs to."""
    return (when or datetime.now(UTC)).astimezone(LAGOS).strftime("%Y-%m")


def window_label(window: str) -> str:
    return datetime.strptime(window, "%Y-%m").strftime("%B %Y")


def naira(amount: float) -> str:
    return f"₦{int(amount):,}"


def ineligible_reason(review: Review, *, banned: bool) -> str | None:
    """Why a published review cannot be entered for a payout, or None when it can."""
    s = get_settings()
    if banned:
        return "banned"
    if review.status != "published":
        return "hidden"
    if (review.extraction.business.country or "").upper() != s.payout_country:
        return "outside_nigeria"
    if review.similarity is not None:
        return "similar"
    if review.source == "reel" and not (review.face_check and review.face_check.passed):
        return "no_face_check"
    return None
