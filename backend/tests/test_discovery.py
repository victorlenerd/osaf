"""The WhatsApp vendor-discovery agent loop and the search query it relies on."""

from __future__ import annotations

import json

import pytest

from app.agent import discover
from app.config import get_settings
from app.models import (
    Conversation,
    DiscoverySession,
    PlaceCandidate,
    SharedLocation,
    ShownVendor,
    now_iso,
)
from app.store import opensearch
from tests.fakes import ScriptedChat, reply, tool_call

SUYA = {
    "business_id": "ChIJsuya",
    "name": "Suya Palace",
    "formatted_address": "Admiralty Way, Lekki, Lagos",
    "city": "Lagos",
    "category": "street_food",
    "review_count": 4,
    "recommend_rate": 0.75,
    "summary_headline": "Spicy suya and quick service",
}
GRILL = {**SUYA, "business_id": "afefe:grill-lagos", "name": "Grill House", "review_count": 1}


def _conv(**kw) -> Conversation:
    return Conversation(phone="2348012345678", profile_country="NG", **kw)


class Searches:
    def __init__(self, *answers: list[dict]):
        self.answers = list(answers)
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, query, **kw):
        self.calls.append((query, kw))
        return self.answers.pop(0) if self.answers else []


def _tool_results(chat: ScriptedChat, call: int) -> list[dict]:
    """The tool messages the model saw at the start of chat call number `call`."""
    return [json.loads(m["content"]) for m in chat.calls[call]["messages"] if m["role"] == "tool"]


def test_hit_is_replied_with_numbered_options():
    search = Searches([SUYA, GRILL])
    msg = "1. *Suya Palace* ...\n2. *Grill House* ..."
    chat = ScriptedChat(
        [
            reply(tool_calls=[tool_call("search_vendors", {"query": "suya", "city": "Lekki"})]),
            reply(
                tool_calls=[
                    tool_call(
                        "reply",
                        {"message": msg, "options": ["ChIJsuya", "afefe:grill-lagos"]},
                        "c2",
                    )
                ]
            ),
        ]
    )
    out = discover.run_discovery_turn(_conv(), "best suya in Lekki", chat=chat, search_fn=search)
    assert out.message == msg and out.searched
    assert search.calls[0] == (
        "suya",
        {"country": None, "category": None, "city": "Lekki", "near": None, "limit": 5},
    )
    row = _tool_results(chat, 1)[0]["results"][0]
    assert row["recommend_pct"] == 75 and row["url"].endswith("/business?id=ChIJsuya")
    assert "score" not in row
    assert [(v.n, v.id, v.source) for v in out.session.shown] == [
        (1, "ChIJsuya", "afefehub"),
        (2, "afefe:grill-lagos", "afefehub"),
    ]
    assert out.session.last_query == "best suya in Lekki"
    assert [t.role for t in out.session.turns] == ["user", "assistant"]


def test_no_hit_falls_back_to_google_labelled_unreviewed():
    google_calls: list = []

    def google(query, region):
        google_calls.append((query, region))
        return [
            PlaceCandidate(place_id="g1", name="Tailor Hub", formatted_address="Wuse 2, Abuja"),
            PlaceCandidate(
                place_id="g2",
                name="Closed Tailor",
                formatted_address="Wuse",
                business_status="CLOSED_PERMANENTLY",
            ),
        ]

    chat = ScriptedChat(
        [
            reply(tool_calls=[tool_call("search_vendors", {"query": "tailor", "city": "Wuse 2"})]),
            reply(
                tool_calls=[
                    tool_call(
                        "search_google", {"query": "tailor Wuse 2", "region_code": "NG"}, "c2"
                    )
                ]
            ),
            reply(
                tool_calls=[
                    tool_call("reply", {"message": "Not yet reviewed…", "options": ["g1"]}, "c3")
                ]
            ),
        ]
    )
    out = discover.run_discovery_turn(
        _conv(), "tailor in Wuse 2", chat=chat, search_fn=Searches([]), google_fn=google
    )
    assert google_calls == [("tailor Wuse 2", "NG")]
    google_result = _tool_results(chat, 2)[-1]
    assert google_result["not_reviewed_on_afefehub"] is True
    assert [r["place_id"] for r in google_result["results"]] == ["g1"]
    assert [(v.id, v.source) for v in out.session.shown] == [("g1", "google")]


def test_google_is_refused_before_an_empty_afefehub_search():
    chat = ScriptedChat(
        [
            reply(tool_calls=[tool_call("search_google", {"query": "x", "region_code": "NG"})]),
            reply(tool_calls=[tool_call("reply", {"message": "Tell me where?"}, "c2")]),
        ]
    )
    out = discover.run_discovery_turn(
        _conv(), "x", chat=chat, google_fn=lambda *a: pytest.fail("google called")
    )
    assert "only allowed after search_vendors" in _tool_results(chat, 1)[0]["error"]
    assert out.message == "Tell me where?"


def test_google_tool_is_withheld_when_disabled(monkeypatch):
    monkeypatch.setattr(get_settings(), "discovery_google_fallback", False)
    chat = ScriptedChat([reply(tool_calls=[tool_call("reply", {"message": "hi"})])])
    discover.run_discovery_turn(_conv(), "hello there", chat=chat)
    names = [t["function"]["name"] for t in chat.calls[0]["tools"]]
    assert "search_google" not in names
    assert "Afefehub has no reviews for that yet" in chat.calls[0]["messages"][0]["content"]


def test_follow_up_number_resolves_to_the_shown_vendor():
    session = DiscoverySession(
        shown=[
            ShownVendor(n=1, id="ChIJsuya", name="Suya Palace"),
            ShownVendor(n=2, id="afefe:grill-lagos", name="Grill House"),
        ],
        last_query="suya in Lekki",
    )
    looked_up: list[str] = []
    chat = ScriptedChat(
        [
            reply(tool_calls=[tool_call("get_vendor", {"business_id": "afefe:grill-lagos"})]),
            reply(tool_calls=[tool_call("reply", {"message": "Grill House: …"}, "c2")]),
        ]
    )
    out = discover.run_discovery_turn(
        _conv(discovery=session),
        "tell me more about 2",
        chat=chat,
        details_fn=lambda bid: looked_up.append(bid) or {"name": "Grill House"},
    )
    ctx = json.loads(chat.calls[0]["messages"][1]["content"])
    assert ctx["options_shown_last_time"][1]["id"] == "afefe:grill-lagos"
    assert looked_up == ["afefe:grill-lagos"]
    # no new options listed: the numbering from last time still holds
    assert [v.id for v in out.session.shown] == ["ChIJsuya", "afefe:grill-lagos"]
    assert out.session.last_query == "suya in Lekki" and not out.searched


def test_unknown_business_id_is_refused():
    chat = ScriptedChat(
        [
            reply(tool_calls=[tool_call("get_vendor", {"business_id": "made-up"})]),
            reply(tool_calls=[tool_call("reply", {"message": "ok"}, "c2")]),
        ]
    )
    discover.run_discovery_turn(
        _conv(), "x", chat=chat, details_fn=lambda bid: pytest.fail("looked up")
    )
    assert "unknown business_id" in _tool_results(chat, 1)[0]["error"]


def test_invented_option_is_rejected_then_falls_back_to_real_results():
    bad = {"message": "1. *Fake Place*", "options": ["invented-id"]}
    chat = ScriptedChat(
        [
            reply(tool_calls=[tool_call("search_vendors", {"query": "suya"})]),
            reply(tool_calls=[tool_call("reply", bad, "c2")]),
            reply(tool_calls=[tool_call("reply", bad, "c3")]),
        ]
    )
    out = discover.run_discovery_turn(_conv(), "suya", chat=chat, search_fn=Searches([SUYA]))
    assert "not returned by any tool" in _tool_results(chat, 2)[-1]["problems"][0]
    assert "1. *Suya Palace*" in out.message and "Fake" not in out.message
    assert [v.id for v in out.session.shown] == ["ChIJsuya"]


def test_plain_text_is_retried_once_then_a_safe_fallback():
    chat = ScriptedChat([reply("Try Mama Cass!"), reply("Seriously, Mama Cass.")])
    out = discover.run_discovery_turn(_conv(), "food?", chat=chat)
    assert "Respond with a tool call" in chat.calls[1]["messages"][-1]["content"]
    assert out.message == discover.FALLBACK_MSG and "Mama Cass" not in out.message


def test_empty_search_and_no_reply_says_no_match():
    chat = ScriptedChat(
        [reply(tool_calls=[tool_call("search_vendors", {"query": "zebra"})])] + [reply("…")] * 2
    )
    out = discover.run_discovery_turn(_conv(), "zebra rides", chat=chat, search_fn=Searches([]))
    assert out.message == discover.NO_MATCH_MSG


def test_search_limit_per_turn():
    calls = [
        reply(tool_calls=[tool_call("search_vendors", {"query": f"q{i}"}, f"c{i}")])
        for i in range(4)
    ]
    chat = ScriptedChat([*calls, reply(tool_calls=[tool_call("reply", {"message": "m"}, "r")])])
    search = Searches()
    discover.run_discovery_turn(_conv(), "x", chat=chat, search_fn=search)
    assert len(search.calls) == discover.MAX_SEARCHES_PER_TURN
    assert "search limit" in _tool_results(chat, 4)[-1]["error"]


def test_near_is_clamped_and_location_is_in_context():
    conv = _conv(last_location=SharedLocation(lat=6.45, lng=3.47))
    chat = ScriptedChat(
        [
            reply(
                tool_calls=[
                    tool_call(
                        "search_vendors",
                        {"query": "pharmacy", "near": {"lat": 6.45, "lng": 3.47, "radius_km": 900}},
                    )
                ]
            ),
            reply(tool_calls=[tool_call("reply", {"message": "m"}, "c2")]),
        ]
    )
    search = Searches()
    discover.run_discovery_turn(conv, "pharmacy near me", chat=chat, search_fn=search)
    assert search.calls[0][1]["near"] == (6.45, 3.47, 50.0)
    ctx = json.loads(chat.calls[0]["messages"][1]["content"])
    assert ctx["shared_location"] == {"lat": 6.45, "lng": 3.47}


def test_stale_session_and_location_are_forgotten():
    old = "2026-01-01T00:00:00Z"
    conv = _conv(
        discovery=DiscoverySession(
            shown=[ShownVendor(n=1, id="x", name="X")], last_query="q", updated_at=old
        ),
        last_location=SharedLocation(lat=1, lng=2, at=old),
    )
    assert discover.live_session(conv) is None and discover.live_location(conv) is None
    conv.discovery.updated_at = now_iso()
    assert discover.live_session(conv) is not None


def test_session_keeps_only_recent_turns():
    session = DiscoverySession(
        turns=[{"role": "user", "text": str(i)} for i in range(10)], last_query="q"
    )
    chat = ScriptedChat([reply(tool_calls=[tool_call("reply", {"message": "m" * 2000})])])
    out = discover.run_discovery_turn(_conv(discovery=session), "y" * 900, chat=chat)
    assert len(out.session.turns) == discover.MAX_TURNS_KEPT
    assert len(out.session.turns[-2].text) == discover.MAX_TURN_CHARS
    assert len(out.message) == discover.MAX_REPLY_CHARS


# ------------------------------------------------------------------ intent check
@pytest.mark.parametrize(
    "text",
    ["2", "number 2", "the second one", "Ikeja", "Allen Avenue branch", "none of them"],
)
def test_obvious_answers(text):
    assert discover.obviously_an_answer(text)


@pytest.mark.parametrize("text", ["any good barber in Yaba?", "where can I get suya around here"])
def test_not_obvious_answers(text):
    assert not discover.obviously_an_answer(text)


def test_classify_intent_reads_json_and_fails_safe():
    chat = ScriptedChat([reply('{"intent": "discover"}')])
    assert discover.classify_intent("any barber in Yaba?", "Which branch?", chat=chat) == "discover"
    kw = chat.calls[0]
    assert kw["reasoning_effort"] == "minimal" and kw["response_format"]["type"] == "json_object"
    assert discover.classify_intent("x", "q", chat=ScriptedChat([reply("nonsense")])) == "answer"

    def boom(*a, **k):
        raise TimeoutError

    assert discover.classify_intent("x", "q", chat=boom) == "answer"


# ------------------------------------------------------------------ search query body
def test_search_body_without_new_filters_keeps_old_ranking():
    body = opensearch.build_search_body("jollof", country="ng", category="restaurant", limit=7)
    fs = body["query"]["function_score"]
    assert body["size"] == 7 and fs["boost_mode"] == "replace"
    assert fs["functions"] == [opensearch.RANK_SCRIPT]
    assert fs["query"]["bool"]["filter"] == [
        {"term": {"country": "NG"}},
        {"term": {"category": "restaurant"}},
    ]
    assert "must_not" not in fs["query"]["bool"]


def test_search_body_city_near_and_exclude():
    body = opensearch.build_search_body(
        "suya", city="Lekki", near=(6.45, 3.47, 4), exclude_ids=["a", "b"]
    )
    fs = body["query"]["function_score"]
    city, geo = fs["query"]["bool"]["filter"]
    shoulds = city["bool"]["should"]
    assert {"term": {"city": "Lekki"}} in shoulds
    assert {"match": {"formatted_address": {"query": "Lekki", "operator": "and"}}} in shoulds
    assert city["bool"]["minimum_should_match"] == 1
    assert geo == {"geo_distance": {"distance": "4km", "location": {"lat": 6.45, "lon": 3.47}}}
    assert fs["query"]["bool"]["must_not"] == [{"ids": {"values": ["a", "b"]}}]
    gauss = fs["functions"][1]["gauss"]["location"]
    assert gauss["origin"] == {"lat": 6.45, "lon": 3.47} and gauss["scale"] == "2.0km"
    assert fs["score_mode"] == "multiply"


def test_search_reports_distance_when_near(monkeypatch):
    class C:
        def search(self, index, body):
            return {
                "hits": {
                    "hits": [
                        {
                            "_score": 1.0,
                            "_source": {
                                "business_id": "b",
                                "name": "B",
                                "location": {"lat": 6.46, "lon": 3.47},
                            },
                        }
                    ]
                }
            }

    monkeypatch.setattr(opensearch, "client", lambda: C())
    rows = opensearch.search("x", near=(6.45, 3.47, 5))
    assert rows[0]["distance_km"] == pytest.approx(1.1, abs=0.05)
    assert "distance_km" not in opensearch.search("x")[0]
