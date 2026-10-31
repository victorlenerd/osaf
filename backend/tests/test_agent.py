import json

from app.agent.extract import run_extraction_turn
from app.agent.summary import generate_summary, summarize_google_reviews
from app.models import (
    Business,
    Conversation,
    GooglePlaceDetails,
    GoogleReview,
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
    assert chat.calls[0]["reasoning_effort"] == "minimal"
    assert s.review_count == 3
    assert s.recommendation_rate == round(2 / 3, 3)
    assert s.last_review_at == "2026-10-03T00:00:00Z"
    assert s.headline == "Great jollof"
    assert chat.calls[0]["response_format"] == {"type": "json_object"}


def test_city_of_handles_junk_locality_and_suffixes():
    from app.agent.places import city_of

    def comp(text, *types):
        return {"longText": text, "shortText": text, "types": list(types)}

    nairobi = {
        "addressComponents": [
            comp("Kilimani", "sublocality"),
            comp("North", "locality"),
            comp("Nairobi County", "administrative_area_level_1"),
        ]
    }
    accra = {"addressComponents": [comp("Osu Klottey", "sublocality"), comp("Accra", "locality")]}
    no_locality = {
        "addressComponents": [comp("Korle Klottey Municipal", "administrative_area_level_2")]
    }
    assert city_of(nairobi) == "Nairobi"
    assert city_of(accra) == "Accra"
    assert city_of(no_locality) == "Korle Klottey"
    assert city_of({}) is None


def test_reject_tool_ends_turn_with_reason():
    chat = ScriptedChat(
        [reply(tool_calls=[tool_call("reject_review", {"reason": "a vlog about EV driving"})])]
    )
    out = run_extraction_turn(
        _sub(), Conversation(phone="x"), None, chat=chat, search_fn=lambda *a, **k: []
    )
    assert out.kind == "reject" and out.reason == "a vlog about EV driving"
    names = [t["function"]["name"] for t in chat.calls[0]["tools"]]
    assert "reject_review" in names
    assert "reject_review immediately" in chat.calls[0]["messages"][0]["content"]


GPLACE = GooglePlaceDetails(
    place_id="ChIJ123",
    name="Mama Put Kitchen",
    formatted_address="12 Allen Ave, Ikeja, Lagos",
    primary_type="restaurant",
    rating=4.4,
    user_rating_count=120,
    reviews=[
        GoogleReview(
            author_name="Ada", rating=5, text="Jollof dey burst brain.", relative_time="a month ago"
        ),
        GoogleReview(
            author_name="Bola",
            rating=4,
            text="Good suya, parking is hard.",
            relative_time="3 months ago",
        ),
        GoogleReview(author_name="Chi", rating=2, text="", relative_time="a year ago"),
    ],
)


def test_google_summary_uses_textual_reviews_and_model_output():
    chat = ScriptedChat(
        [
            reply(
                json.dumps(
                    {
                        "overall_sentiment": "mixed",
                        "headline": "Loved for jollof and suya; parking is a struggle",
                        "recurring_praise": ["jollof", "suya", 7, {"bad": 1}],
                        "recurring_complaints": ["parking"],
                        "standout_items": ["jollof rice", "suya"],
                    }
                )
            )
        ]
    )
    s = summarize_google_reviews(GPLACE, chat=chat)
    assert s.overall_sentiment == "mixed"
    assert s.headline.startswith("Loved for jollof")
    assert s.recurring_praise == ["jollof", "suya", "7"]  # dicts dropped, scalars kept
    assert s.recurring_complaints == ["parking"] and s.standout_items == ["jollof rice", "suya"]
    assert s.rating == 4.4 and s.user_rating_count == 120 and s.reviews_considered == 2
    assert s.expires_at is None  # the store sets the TTL
    payload = json.loads(chat.calls[0]["messages"][1]["content"])
    assert [r["text"] for r in payload["reviews"]] == [
        "Jollof dey burst brain.",
        "Good suya, parking is hard.",
    ]
    assert chat.calls[0]["response_format"] == {"type": "json_object"}


def test_google_summary_falls_back_to_rating_when_model_fails():
    s = summarize_google_reviews(GPLACE, chat=ScriptedChat([]))
    assert s.overall_sentiment == "positive" and s.headline == "" and s.reviews_considered == 2
    low = GPLACE.model_copy(update={"rating": 2.0})
    assert summarize_google_reviews(low, chat=ScriptedChat([])).overall_sentiment == "negative"
    unrated = GPLACE.model_copy(update={"rating": None})
    assert summarize_google_reviews(unrated, chat=ScriptedChat([])).overall_sentiment == "mixed"


def test_google_summary_skips_model_without_textual_reviews():
    chat = ScriptedChat([])
    bare = GPLACE.model_copy(update={"reviews": [GoogleReview(rating=4)]})
    s = summarize_google_reviews(bare, chat=chat)
    assert chat.calls == [] and s.reviews_considered == 0 and s.overall_sentiment == "positive"
