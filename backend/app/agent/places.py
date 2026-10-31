"""Google Places API (New): text search (the agent's business-resolution tool) and Place Details
(on-demand Google reviews for the public site)."""

from __future__ import annotations

import logging

import httpx
import phonenumbers

from app.config import get_settings
from app.models import GooglePlaceDetails, GoogleReview, PlaceCandidate

log = logging.getLogger(__name__)

FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.primaryType",
        "places.types",
        "places.addressComponents",
        "places.businessStatus",
    ]
)

# Place Details masks are unprefixed. `reviews` is the Enterprise + Atmosphere SKU: call it only
# from the on-demand endpoint, never from the agent.
DETAILS_FIELD_MASK = ",".join(
    [
        "id",
        "displayName",
        "formattedAddress",
        "location",
        "addressComponents",
        "primaryType",
        "rating",
        "userRatingCount",
        "googleMapsUri",
        "businessStatus",
        "reviews",
    ]
)
PLACES_BASE = "https://places.googleapis.com/v1"


def country_from_phone(phone: str) -> str | None:
    try:
        num = phonenumbers.parse("+" + phone.lstrip("+"))
        return phonenumbers.region_code_for_number(num)
    except phonenumbers.NumberParseException:
        return None


def _component(place: dict, kind: str, *, short: bool = False) -> str | None:
    for c in place.get("addressComponents") or []:
        if kind in (c.get("types") or []):
            if short:
                return c.get("shortText") or c.get("longText")
            return c.get("longText") or c.get("shortText")
    return None


# Google sometimes fills `locality` with a compass-point ward name (Nairobi: "North").
_JUNK_LOCALITIES = {"north", "south", "east", "west", "central", "northern", "southern"}
_AREA_SUFFIXES = (" County", " Municipal", " Municipality", " District", " Region", " State")


def city_of(place: dict) -> str | None:
    """Best-effort city: locality, else a cleaned admin area, else sublocality."""
    loc = _component(place, "locality")
    if loc and loc.strip().lower() not in _JUNK_LOCALITIES:
        return loc
    for kind in ("administrative_area_level_1", "administrative_area_level_2"):
        area = _component(place, kind)
        if area:
            for suf in _AREA_SUFFIXES:
                if area.endswith(suf):
                    area = area[: -len(suf)]
            return area
    return loc or _component(place, "sublocality")


def search_places(
    query: str,
    region_code: str,
    *,
    lat: float | None = None,
    lng: float | None = None,
    radius_m: int = 20000,
    max_results: int = 5,
) -> list[PlaceCandidate]:
    key = get_settings().google_places_api_key
    if not key:
        raise RuntimeError("GOOGLE_PLACES_API_KEY not configured")
    body: dict = {
        "textQuery": query,
        "regionCode": (region_code or "").upper() or None,
        "languageCode": "en",
        "maxResultCount": max_results,
    }
    if lat is not None and lng is not None:
        body["locationBias"] = {
            "circle": {"center": {"latitude": lat, "longitude": lng}, "radius": float(radius_m)}
        }
    body = {k: v for k, v in body.items() if v is not None}
    r = httpx.post(
        "https://places.googleapis.com/v1/places:searchText",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": FIELD_MASK,
        },
        json=body,
        timeout=20,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"Places error {r.status_code}: {r.text[:300]}")
    out: list[PlaceCandidate] = []
    for p in r.json().get("places", []):
        loc = p.get("location") or {}
        out.append(
            PlaceCandidate(
                place_id=p["id"],
                name=(p.get("displayName") or {}).get("text") or "",
                formatted_address=p.get("formattedAddress") or "",
                lat=loc.get("latitude"),
                lng=loc.get("longitude"),
                country=_component(p, "country"),
                city=city_of(p),
                primary_type=p.get("primaryType"),
                business_status=p.get("businessStatus"),
            )
        )
    return out


def _review(r: dict) -> GoogleReview:
    text = r.get("text") or r.get("originalText") or {}
    author = r.get("authorAttribution") or {}
    return GoogleReview(
        author_name=author.get("displayName") or "",
        author_uri=author.get("uri"),
        author_photo_uri=author.get("photoUri"),
        rating=r.get("rating"),
        text=text.get("text") or "",
        language=text.get("languageCode"),
        relative_time=r.get("relativePublishTimeDescription") or "",
        publish_time=r.get("publishTime"),
        google_maps_uri=r.get("googleMapsUri"),
    )


def get_place_details(place_id: str) -> GooglePlaceDetails | None:
    """Live Place Details incl. up to 5 reviews. None when Google does not know the id."""
    key = get_settings().google_places_api_key
    if not key:
        raise RuntimeError("GOOGLE_PLACES_API_KEY not configured")
    r = httpx.get(
        f"{PLACES_BASE}/places/{place_id}",
        headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": DETAILS_FIELD_MASK},
        params={"languageCode": "en"},
        timeout=20,
    )
    if r.status_code in (400, 404):  # INVALID_ARGUMENT (malformed id) or NOT_FOUND
        log.info("place details %s -> %s", place_id, r.status_code)
        return None
    if r.status_code >= 400:
        raise RuntimeError(f"Places error {r.status_code}: {r.text[:300]}")
    p = r.json()
    loc = p.get("location") or {}
    return GooglePlaceDetails(
        place_id=place_id,  # keep the requested id: Google may hand back a refreshed one
        name=(p.get("displayName") or {}).get("text") or "",
        formatted_address=p.get("formattedAddress") or "",
        city=city_of(p),
        country=_component(p, "country", short=True),  # alpha-2, as the site expects
        lat=loc.get("latitude"),
        lng=loc.get("longitude"),
        primary_type=p.get("primaryType"),
        rating=p.get("rating"),
        user_rating_count=int(p.get("userRatingCount") or 0),
        google_maps_uri=p.get("googleMapsUri"),
        business_status=p.get("businessStatus"),
        reviews=[_review(x) for x in p.get("reviews") or []],
    )
