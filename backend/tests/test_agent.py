import json

from app.agent.extract import run_extraction_turn
from app.agent.summary import generate_summary
from app.models import (
    Business,
    Conversation,
    PlaceCandidate,
    PlaceRef,
    Review,
    ReviewExtraction,
    Submission,
    Transcript,
)
from tests.fakes import ScriptedChat, reply, tool_call

MAMA_PUT = PlaceCandidate(
    place_id="ChIJ123",
    name="Mama Put Kitchen",
    formatted_address="12 Allen Ave, Ikeja, Lagos",
    lat=6.6,
    lng=3.35,
    country="NG",
    city="Ikeja",
    primary_type="restaurant",
)

FINAL_ARGS = {
    "business": {
        "place_id": "ChIJ123",
        "name": "Mama Put",
        "formatted_address": "Allen Ave",
        "country": "NG",
        "source": "google",
    },
    "business_name_as_said": "Mama Put",
    "visit": {"when_text": "last Saturday"},
    "good": ["jollof was smoky"],
    "improve": ["slow service"],
    "recommend": "yes",
    "category": "restaurant",
    "keywords": ["jollof", "suya"],
    "overall_sentiment": "positive",
    "language": "pcm",
    "confidence": {"business": 0.9},
    "one_line_summary": "Smoky jollof, slow service, would go back",
}


def _sub(**kw) -> Submission:
    return Submission(
        submission_id="s1",
        phone="2348000000000",
        reel_url="https://www.instagram.com/reel/abc/",
        reel_shortcode="abc",
        transcript=Transcript(text="I went to Mama Put on Allen Avenue, jollof was smoky"),
        **kw,
    )


def test_search_then_finalize_uses_candidate_details():
    chat = ScriptedChat(
        [
            reply(
                tool_calls=[
                    tool_call("search_places", {"query": "Mama Put Allen", "region_code": "NG"})
                ]
            ),
            reply(tool_calls=[tool_call("finalize_review", FINAL_ARGS, "call_2")]),
        ]
    )
    out = run_extraction_turn(
        _sub(),
        Conversation(phone="x", profile_country="NG"),
        None,
        chat=chat,
        search_fn=lambda *a, **k: [MAMA_PUT],
    )
    assert out.kind == "final"
    assert out.extraction.business.name == "Mama Put Kitchen"
    assert out.extraction.business.city == "Ikeja"
    assert out.extraction.business.source == "google"
    # the tool result was fed back to the model
    tool_msgs = [m for m in chat.calls[1]["messages"] if m["role"] == "tool"]
    assert json.loads(tool_msgs[0]["content"])["results"][0]["place_id"] == "ChIJ123"


def test_invented_place_id_is_rejected_then_asks():
    bad = {**FINAL_ARGS, "business": {**FINAL_ARGS["business"], "place_id": "ChIJ_FAKE"}}
    chat = ScriptedChat(
        [
            reply(tool_calls=[tool_call("finalize_review", bad)]),
            reply(tool_calls=[tool_call("finalize_review", bad, "call_2")]),
        ]
    )
    out = run_extraction_turn(
        _sub(), Conversation(phone="x"), None, chat=chat, search_fn=lambda *a, **k: []
    )
    assert out.kind == "ask"
    assert "business" in out.missing_fields
    err = json.loads([m for m in chat.calls[1]["messages"] if m["role"] == "tool"][0]["content"])
    assert err["error"] == "invalid"


def test_ask_user_returns_question_and_candidates():
    chat = ScriptedChat(
        [
            reply(
                tool_calls=[tool_call("search_places", {"query": "Mama Put", "region_code": "NG"})]
            ),
            reply(
                tool_calls=[
                    tool_call(
                        "ask_user",
                        {
                            "question": "Which one? 1. A 2. B",
                            "missing_fields": ["business"],
                            "candidates_shown": ["ChIJ123"],
                        },
                        "call_2",
                    )
                ]
            ),
        ]
    )
    out = run_extraction_turn(
        _sub(), Conversation(phone="x"), None, chat=chat, search_fn=lambda *a, **k: [MAMA_PUT]
    )
    assert out.kind == "ask"
    assert out.question.startswith("Which one?")
    assert out.place_candidates[0].place_id == "ChIJ123"
    assert out.collected["_search_attempts"] == 1


def test_round_cap_removes_ask_tool():
    chat = ScriptedChat([reply(content="REJECT: nothing about a business")])
    out = run_extraction_turn(
        _sub(clarification_rounds=3),
        Conversation(phone="x"),
        "dunno",
        chat=chat,
        search_fn=lambda *a, **k: [],
    )
    assert out.kind == "reject"
    names = [t["function"]["name"] for t in chat.calls[0]["tools"]]
    assert "ask_user" not in names
    assert "0 question(s) left" in chat.calls[0]["messages"][0]["content"]


def test_user_sourced_business_requires_two_searches():
    user_biz = {
        **FINAL_ARGS,
        "business": {
            "place_id": "afefe:iya-oyo-ikeja",
            "name": "Iya Oyo",
            "formatted_address": "behind Ikeja bus stop",
            "country": "NG",
            "city": "Ikeja",
            "source": "user",
        },
    }
    chat = ScriptedChat(
        [
            reply(
                tool_calls=[
                    tool_call("search_places", {"query": "Iya Oyo", "region_code": "NG"}, "c1")
                ]
            ),
            reply(
                tool_calls=[
                    tool_call(
                        "search_places", {"query": "Iya Oyo Ikeja", "region_code": "NG"}, "c2"
                    )
                ]
            ),
            reply(tool_calls=[tool_call("finalize_review", user_biz, "c3")]),
        ]
    )
    out = run_extraction_turn(
        _sub(), Conversation(phone="x"), None, chat=chat, search_fn=lambda *a, **k: []
    )
    assert out.kind == "final"
    assert out.extraction.business.source == "user"
    assert out.extraction.business.place_id == "afefe:iya-oyo-ikeja"


def test_summary_merges_model_output_with_computed_counts():
    ext = ReviewExtraction(**{**FINAL_ARGS, "business": PlaceRef(**FINAL_ARGS["business"])})
    reviews = [
        Review(
            review_id=f"r{i}",
            business_id="ChIJ123",
            submission_id=f"s{i}",
            reviewer_phone_hash="h",
            reel_url="u",
            reel_shortcode=f"sc{i}",
            extraction=ext,
            created_at=f"2026-10-0{i + 1}T00:00:00Z",
        )
        for i in range(3)
    ]
    reviews[2].extraction = ext.model_copy(update={"recommend": "no"})
    chat = ScriptedChat(
        [
            reply(
                content=json.dumps(
                    {
                        "overall_sentiment": "positive",
                        "headline": "Great jollof",
                        "recurring_praise": ["jollof"],
                        "recurring_complaints": [],
                        "standout_items": ["jollof", "suya"],
                    }
                )
            )
        ]
    )
    biz = Business(
        business_id="ChIJ123", name="Mama Put Kitchen", formatted_address="x", country="NG"
    )
    s = generate_summary(biz, reviews, None, chat=chat)
    assert s.review_count == 3
    assert s.recommendation_rate == round(2 / 3, 3)
    assert s.last_review_at == "2026-10-03T00:00:00Z"
    assert s.headline == "Great jollof"
    assert chat.calls[0]["response_format"] == {"type": "json_object"}
