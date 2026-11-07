"""Direct access for AI agents: the public API additions (canonical urls, lookup by slug, top
businesses, the curated OpenAPI spec) and the read-only MCP server at /mcp."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import mcp_server
from app.api import public
from app.main import app
from app.models import Business, BusinessSummary, PlaceRef, Review, ReviewExtraction

MCP_HEADERS = {
    "accept": "application/json, text/event-stream",
    "content-type": "application/json",
    "mcp-protocol-version": "2025-06-18",
}


def _biz(bid, name, yes, no=0, city="Lagos", category="restaurant", **kw):
    return Business(
        business_id=bid,
        name=name,
        formatted_address="a",
        country="NG",
        city=city,
        category=category,
        review_count=yes + no,
        recommend_counts={"yes": yes, "no": no, "maybe": 0},
        **kw,
    )


class Store:
    def __init__(self):
        self.businesses = {
            "g1": _biz("g1", "Mama Cass", 6, rating_sum=14, rating_count=3),
            "g2": _biz("g2", "Yellow Chilli", 2, 2),
            "g3": _biz("g3", "Hotel X", 3, city="Abuja", category="hotel"),
            "afefe:demo-z": _biz("afefe:demo-z", "Demo Z", 50),  # fictional seed row
        }
        self.reviews = {
            "g1": [
                Review(
                    review_id="r1",
                    business_id="g1",
                    submission_id="s1",
                    reviewer_phone_hash="SECRET-HASH",
                    reviewer_display_name="Ada",
                    reel_shortcode="ABC",
                    reel_url="https://www.instagram.com/reel/ABC/",
                    extraction=ReviewExtraction(
                        business=PlaceRef(
                            place_id="g1", name="Mama Cass", formatted_address="a", country="NG"
                        ),
                        business_name_as_said="mama cass",
                        recommend="yes",
                        rating=5,
                        good=["jollof"],
                        one_line_summary="Great jollof.",
                    ),
                )
            ]
        }

    def get_business(self, bid):
        return self.businesses.get(bid)

    def get_business_by_slug(self, slug):
        return next((b for b in self.businesses.values() if b.slug == slug), None)

    def list_reviews(self, bid, limit=100):
        return self.reviews.get(bid, [])

    def get_summary(self, bid):
        return BusinessSummary(headline=f"{bid} headline", recurring_praise=["food"])

    def list_all_businesses(self):
        return list(self.businesses.values())


@pytest.fixture
def store(monkeypatch):
    s = Store()
    monkeypatch.setattr(public, "dynamo", s)
    monkeypatch.setattr(mcp_server, "dynamo", s)
    public._top_cache.clear()
    return s


@pytest.fixture(scope="module")
def client():
    # One lifespan per process: the MCP session manager can only be started once.
    with TestClient(app) as c:
        yield c


def test_business_by_slug_carries_canonical_url_and_rating(store, client):
    slug = store.businesses["g1"].slug
    r = client.get(f"/api/business/by-slug/{slug}")
    assert r.status_code == 200
    b = r.json()["business"]
    assert b["url"] == f"https://afefehub.com/b/{slug}" and b["slug"] == slug
    assert b["average_rating"] == 4.67 and b["rating_count"] == 3
    assert r.json()["reviews"][0]["extraction"]["rating"] == 5
    assert "SECRET-HASH" not in r.text
    assert client.get("/api/business/by-slug/nope-123456").status_code == 404
    # the id route still works
    assert client.get("/api/business/g1").json()["business"]["slug"] == slug


def test_top_ranks_and_filters(store, client):
    r = client.get("/api/top", params={"country": "ng", "city": "lagos", "category": "restaurant"})
    assert r.status_code == 200
    assert [x["name"] for x in r.json()["results"]] == ["Mama Cass", "Yellow Chilli"]
    assert r.json()["where"] == "lagos, Nigeria"
    hotels = client.get("/api/top", params={"country": "NG", "category": "hotel"}).json()
    assert [x["name"] for x in hotels["results"]] == ["Hotel X"]
    assert client.get("/api/top", params={"country": "NG", "category": "x"}).status_code == 400


def test_search_results_carry_url(store, client, monkeypatch):
    row = {"business_id": "g1", "name": "Mama Cass", "city": "Lagos", "country": "NG"}
    monkeypatch.setattr(public.opensearch, "search", lambda *a, **k: [row])
    res = client.get("/api/search", params={"q": "jollof"}).json()["results"][0]
    assert res["url"] == f"https://afefehub.com/b/{store.businesses['g1'].slug}"


def test_public_openapi_has_only_afefehub_read_endpoints(client):
    spec = client.get("/api/openapi-public.json").json()
    assert spec["servers"] == [{"url": "https://api.afefehub.com"}]
    assert set(spec["paths"]) == {
        "/api/search",
        "/api/categories",
        "/api/business/by-slug/{slug}",
        "/api/business/{business_id}",
        "/api/top",
    }
    ops = {op["operationId"] for p in spec["paths"].values() for op in p.values()}
    assert ops == public.PUBLIC_OPERATIONS
    assert "places" not in json.dumps(spec["paths"]) and "webhooks" not in json.dumps(spec)


# ----------------------------------------------------------------------------- MCP
def _rpc(client, method, params=None, id_=1):
    r = client.post(
        "/mcp",
        headers=MCP_HEADERS,
        json={"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}},
    )
    assert r.status_code == 200, r.text
    return r.json()["result"]


def _call(client, name, args):
    result = _rpc(client, "tools/call", {"name": name, "arguments": args})
    return json.loads(result["content"][0]["text"])


def test_mcp_lists_read_only_tools(client):
    _rpc(
        client,
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "t", "version": "1"},
        },
    )
    tools = {t["name"]: t for t in _rpc(client, "tools/list")["tools"]}
    assert set(tools) == {
        "search_businesses",
        "get_business",
        "top_businesses",
        "how_to_submit_review",
    }
    assert all(t["annotations"]["readOnlyHint"] for t in tools.values())


def test_mcp_get_business_by_url_returns_afefehub_data_only(store, client):
    slug = store.businesses["g1"].slug
    out = _call(client, "get_business", {"business": f"https://afefehub.com/b/{slug}.md"})
    assert out["business"]["name"] == "Mama Cass"
    assert out["business"]["url"].endswith(slug)
    assert out["reviews"][0] == {
        "date": out["reviews"][0]["date"],
        "kind": "video",
        "reviewer": "Ada",
        "recommend": "yes",
        "rating": 5,
        "summary": "Great jollof.",
        "good": ["jollof"],
        "could_improve": [],
        "reel_url": "https://www.instagram.com/reel/ABC/",
    }
    assert "Afefehub" in out["attribution"]
    text = json.dumps(out)
    assert "SECRET-HASH" not in text and "google" not in text.lower()
    # by slug and by id too; unknown is a clean error
    assert _call(client, "get_business", {"business": slug})["business"]["name"] == "Mama Cass"
    assert _call(client, "get_business", {"business": "g2"})["business"]["name"] == "Yellow Chilli"
    assert "error" in _call(client, "get_business", {"business": "zzz"})
    assert "error" in _call(client, "get_business", {"business": "afefe:demo-z"})


def test_mcp_top_and_search(store, client, monkeypatch):
    out = _call(client, "top_businesses", {"country": "NG", "city": "Lagos"})
    assert [r["name"] for r in out["results"]] == ["Mama Cass", "Yellow Chilli"]
    assert "error" in _call(client, "top_businesses", {"country": "Nigeria"})

    seen = {}

    def fake_search(q, **kw):
        seen.update(q=q, **kw)
        return [{"business_id": "g1", "name": "Mama Cass", "city": "Lagos", "country": "NG"}]

    monkeypatch.setattr(mcp_server.opensearch, "search", fake_search)
    out = _call(client, "search_businesses", {"query": "jollof", "city": "Lagos", "limit": 99})
    assert seen == {"q": "jollof Lagos", "country": None, "category": None, "limit": 20}
    assert out["results"][0]["url"].startswith("https://afefehub.com/b/mama-cass-lagos-")


def test_mcp_how_to_submit(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "whatsapp_public_number", "+234 803 174 9669")
    out = _call(client, "how_to_submit_review", {})
    assert out["whatsapp_link"] == "https://wa.me/2348031749669"
