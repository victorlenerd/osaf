"""Place Details (New) client: parsing, 'unknown place' handling and error mapping."""

import httpx
import pytest
import respx

from app.agent import places
from app.config import get_settings

URL = "https://places.googleapis.com/v1/places/ChIJabc"

DETAILS = {
    "id": "ChIJabc-refreshed",
    "displayName": {"text": "Mama Put Kitchen", "languageCode": "en"},
    "formattedAddress": "12 Allen Ave, Ikeja, Lagos, Nigeria",
    "location": {"latitude": 6.6, "longitude": 3.35},
    "addressComponents": [
        {"longText": "Ikeja", "shortText": "Ikeja", "types": ["locality"]},
        {"longText": "Nigeria", "shortText": "NG", "types": ["country"]},
    ],
    "primaryType": "restaurant",
    "rating": 4.3,
    "userRatingCount": 812,
    "googleMapsUri": "https://maps.google.com/?cid=1",
    "businessStatus": "OPERATIONAL",
    "reviews": [
        {
            "name": "places/ChIJabc/reviews/r1",
            "relativePublishTimeDescription": "2 months ago",
            "rating": 5,
            "text": {"text": "Best jollof in Ikeja, go early.", "languageCode": "en"},
            "originalText": {"text": "Best jollof in Ikeja, go early.", "languageCode": "en"},
            "authorAttribution": {
                "displayName": "Ada O.",
                "uri": "https://www.google.com/maps/contrib/1",
                "photoUri": "https://lh3.googleusercontent.com/a",
            },
            "publishTime": "2026-08-20T10:00:00Z",
            "googleMapsUri": "https://www.google.com/maps/reviews/r1",
        },
        {
            "name": "places/ChIJabc/reviews/r2",
            "relativePublishTimeDescription": "a year ago",
            "rating": 3,
            "authorAttribution": {"displayName": "Tunde"},
            "publishTime": "2025-08-20T10:00:00Z",
        },
    ],
}


@respx.mock
def test_details_parse_full_payload():
    respx.get(URL).mock(return_value=httpx.Response(200, json=DETAILS))
    d = places.get_place_details("ChIJabc")
    assert d is not None
    assert d.place_id == "ChIJabc"  # the requested id, not Google's refreshed one
    assert d.name == "Mama Put Kitchen"
    assert d.city == "Ikeja" and d.country == "NG"
    assert d.lat == 6.6 and d.lng == 3.35
    assert d.rating == 4.3 and d.user_rating_count == 812
    assert d.business_status == "OPERATIONAL"
    assert d.google_maps_uri == "https://maps.google.com/?cid=1"
    assert len(d.reviews) == 2
    r1, r2 = d.reviews
    assert r1.author_name == "Ada O." and r1.author_uri.endswith("/contrib/1")
    assert r1.rating == 5 and r1.text.startswith("Best jollof") and r1.language == "en"
    assert r1.relative_time == "2 months ago" and r1.publish_time == "2026-08-20T10:00:00Z"
    assert r2.text == "" and r2.rating == 3 and r2.author_uri is None  # rating-only review

    req = respx.calls.last.request
    assert req.headers["X-Goog-Api-Key"] == "test"
    assert "reviews" in req.headers["X-Goog-FieldMask"].split(",")
    assert req.url.params["languageCode"] == "en"


@respx.mock
def test_details_without_reviews_key_gives_empty_list():
    body = {k: v for k, v in DETAILS.items() if k != "reviews"}
    respx.get(URL).mock(return_value=httpx.Response(200, json=body))
    d = places.get_place_details("ChIJabc")
    assert d is not None and d.reviews == []


@respx.mock
@pytest.mark.parametrize("status", [400, 404])
def test_details_unknown_or_malformed_id_is_none(status):
    respx.get(URL).mock(return_value=httpx.Response(status, json={"error": {"status": "X"}}))
    assert places.get_place_details("ChIJabc") is None


@respx.mock
def test_details_server_error_raises():
    respx.get(URL).mock(return_value=httpx.Response(500, text="boom"))
    with pytest.raises(RuntimeError, match="Places error 500"):
        places.get_place_details("ChIJabc")


def test_details_requires_api_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="not configured"):
            places.get_place_details("ChIJabc")
    finally:
        get_settings.cache_clear()


@respx.mock
def test_text_search_carries_business_status():
    respx.post("https://places.googleapis.com/v1/places:searchText").mock(
        return_value=httpx.Response(
            200,
            json={
                "places": [
                    {
                        "id": "ChIJx",
                        "displayName": {"text": "Closed Spot"},
                        "formattedAddress": "Somewhere",
                        "businessStatus": "CLOSED_PERMANENTLY",
                    }
                ]
            },
        )
    )
    [c] = places.search_places("closed spot", "NG")
    assert c.business_status == "CLOSED_PERMANENTLY"
    assert "places.businessStatus" in respx.calls.last.request.headers["X-Goog-FieldMask"]
