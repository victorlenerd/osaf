"""Public endpoints for Google-verified places and their on-demand reviews."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from app.agent import summary as summary_mod
from app.api import public
from app.models import GooglePlaceDetails, GoogleReview, GoogleReviewSummary, PlaceCandidate
from tests.fakes import ScriptedChat, reply

PLACE = GooglePlaceDetails(
    place_id="ChIJabc",
    name="Mama Put Kitchen",
    formatted_address="12 Allen Ave, Ikeja, Lagos",
    city="Ikeja",
    country="NG",
    lat=6.6,
    lng=3.35,
    primary_type="restaurant",
    rating=4.3,
    user_rating_count=812,
    google_maps_uri="https://maps.google.com/?cid=1",
    business_status="OPERATIONAL",
    reviews=[
        GoogleReview(
            author_name="Ada", rating=5, text="Best jollof.", relative_time="2 months ago"
        ),
        GoogleReview(author_name="Tunde", rating=3, text="", relative_time="a year ago"),
    ],
)
LLM_JSON = json.dumps(
    {
        "overall_sentiment": "positive",
        "headline": "Loved for its jollof",
        "recurring_praise": ["jollof"],
        "recurring_complaints": [],
        "standout_items": ["jollof rice"],
    }
)


class MemStore:
    def __init__(self):
        self.items: dict[str, GoogleReviewSummary] = {}

    def get_google_summary(self, pid):
        s = self.items.get(pid)
        if s and s.expires_at and s.expires_at > int(time.time()):
            return s
        return None

    def put_google_summary(self, pid, s):
        if s.expires_at is None:
            s.expires_at = int(time.time()) + 86400
        self.items[pid] = s


@pytest.fixture
def world(monkeypatch):
    from app.main import app

    store = MemStore()
    chat = ScriptedChat([reply(LLM_JSON)])
    google_calls: list = []
    monkeypatch.setattr(public, "dynamo", store)
    monkeypatch.setattr(public, "google_bucket", public._TokenBucket(60))
    monkeypatch.setattr(public, "get_place_details", lambda pid: google_calls.append(pid) or PLACE)
    monkeypatch.setattr(
        public,
        "search_places",
        lambda q, region, **k: (
            google_calls.append((q, region, k))
            or [PlaceCandidate(place_id="ChIJabc", name="Mama Put Kitchen", formatted_address="x")]
        ),
    )
    monkeypatch.setattr(summary_mod, "get_meta", lambda: type("M", (), {"chat": chat})())
    c = TestClient(app)
    return c, store, chat, google_calls


def test_lookup_returns_candidates(world):
    c, _, _, calls = world
    r = c.get("/api/places/lookup", params={"q": " mama put ", "country": "NG", "limit": 3})
    assert r.status_code == 200
    assert r.json()["candidates"][0]["place_id"] == "ChIJabc"
    assert calls == [("mama put", "NG", {"max_results": 3})]


def test_lookup_validates_query(world):
    c, *_ = world
    assert c.get("/api/places/lookup", params={"q": "a"}).status_code == 422


def test_lookup_maps_missing_key_to_503_and_upstream_to_502(world, monkeypatch):
    c, *_ = world

    def boom(*a, **k):
        raise RuntimeError("GOOGLE_PLACES_API_KEY not configured")

    monkeypatch.setattr(public, "search_places", boom)
    assert c.get("/api/places/lookup", params={"q": "mama"}).status_code == 503

    def upstream(*a, **k):
        raise RuntimeError("Places error 500: boom")

    monkeypatch.setattr(public, "search_places", upstream)
    assert c.get("/api/places/lookup", params={"q": "mama"}).status_code == 502


def test_google_reviews_cache_miss_then_hit(world):
    c, store, chat, calls = world
    r = c.get("/api/places/ChIJabc/google")
    assert r.status_code == 200
    body = r.json()
    assert body["attribution"] == "Reviews from Google"
    assert body["place"]["name"] == "Mama Put Kitchen" and "reviews" not in body["place"]
    assert [x["author_name"] for x in body["reviews"]] == ["Ada", "Tunde"]
    assert body["summary"]["headline"] == "Loved for its jollof"
    assert body["summary"]["overall_sentiment"] == "positive"
    assert body["summary"]["reviews_considered"] == 1  # the rating-only review is not text
    assert body["summary"]["rating"] == 4.3 and body["summary"]["user_rating_count"] == 812
    assert "expires_at" not in body["summary"]
    assert store.items["ChIJabc"].expires_at > int(time.time()) + 86000
    assert len(chat.calls) == 1
    sent = json.loads(chat.calls[0]["messages"][1]["content"])
    assert [x["text"] for x in sent["reviews"]] == ["Best jollof."]
    assert chat.calls[0]["timeout"] == 20
    assert chat.calls[0]["reasoning_effort"] == "minimal"

    # Second view: reviews fetched live again, summary served from cache (no LLM call).
    r2 = c.get("/api/places/ChIJabc/google")
    assert r2.status_code == 200
    assert r2.json()["summary"]["generated_at"] == body["summary"]["generated_at"]
    assert len(chat.calls) == 1
    assert calls == ["ChIJabc", "ChIJabc"]


def test_google_reviews_expired_cache_is_regenerated(world):
    c, store, chat, _ = world
    stale = GoogleReviewSummary(
        headline="old", reviews_considered=1, expires_at=int(time.time()) - 5
    )
    store.items["ChIJabc"] = stale
    r = c.get("/api/places/ChIJabc/google")
    assert r.json()["summary"]["headline"] == "Loved for its jollof"
    assert len(chat.calls) == 1


def test_google_reviews_llm_failure_is_rating_only_and_not_cached(world, monkeypatch):
    c, store, _, _ = world
    broken = ScriptedChat([])  # raises when called
    monkeypatch.setattr(summary_mod, "get_meta", lambda: type("M", (), {"chat": broken})())
    r = c.get("/api/places/ChIJabc/google")
    assert r.status_code == 200
    s = r.json()["summary"]
    assert s["headline"] == "" and s["overall_sentiment"] == "positive"  # from the 4.3 rating
    assert store.items == {}


def test_google_reviews_unknown_and_afefe_ids_are_404(world, monkeypatch):
    c, _, _, calls = world
    assert c.get("/api/places/afefe:mama-put-lagos/google").status_code == 404
    assert calls == []  # never hits Google for user-sourced ids
    monkeypatch.setattr(public, "get_place_details", lambda pid: None)
    assert c.get("/api/places/ChIJnope/google").status_code == 404


def test_google_calls_are_rate_limited(world, monkeypatch):
    c, *_ = world
    monkeypatch.setattr(public, "google_bucket", public._TokenBucket(2))
    assert c.get("/api/places/lookup", params={"q": "mama"}).status_code == 200
    assert c.get("/api/places/lookup", params={"q": "mama"}).status_code == 200
    assert c.get("/api/places/lookup", params={"q": "mama"}).status_code == 429
