"""Google Places API (New) text search — the agent's business-resolution tool."""

from __future__ import annotations

import logging

import httpx
import phonenumbers

from app.config import get_settings
from app.models import PlaceCandidate

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
    ]
)


def country_from_phone(phone: str) -> str | None:
    try:
        num = phonenumbers.parse("+" + phone.lstrip("+"))
        return phonenumbers.region_code_for_number(num)
    except phonenumbers.NumberParseException:
        return None


def _component(place: dict, kind: str) -> str | None:
    for c in place.get("addressComponents") or []:
        if kind in (c.get("types") or []):
            return c.get("shortText") or c.get("longText")
    return None


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
                city=_component(p, "locality")
                or _component(p, "sublocality")
                or _component(p, "administrative_area_level_2"),
                primary_type=p.get("primaryType"),
            )
        )
    return out
