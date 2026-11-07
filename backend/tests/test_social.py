"""Weekly Instagram highlights: window, eligibility, attribution, caption, flags, renderer.
No network: flags use the offline chip, fonts and logos are vendored."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from PIL import Image

from app.models import PlaceRef, Review, ReviewExtraction
from app.social import caption as cap
from app.social.candidates import (
    ANONYMOUS,
    Candidate,
    Window,
    default_window,
    eligible,
    first_name,
    in_window,
    select_candidates,
    to_candidate,
    window_from_dates,
    window_label,
)
from app.social.flags import chip_fallback, flag_emoji, flag_image, twemoji_name
from app.social.render import FONTS, H, W, category_label, render_carousel

PLACE = PlaceRef(
    place_id="ChIJ-lagos-1",
    name="Amala Corner Surulere",
    formatted_address="14 Adelabu Street, Surulere, Lagos, Nigeria",
    country="NG",
    city="Lagos",
)


def review(
    rid: str = "r1",
    *,
    created_at: str = "2026-10-21T12:00:00Z",
    summary: str = "Proper Surulere amala worth the twenty-minute queue.",
    name: str | None = "Tola Adeyemi",
    country: str | None = "NG",
    status: str = "published",
    business: PlaceRef = PLACE,
    good: list[str] | None = None,
    recommend: str = "yes",
) -> Review:
    return Review(
        review_id=rid,
        business_id=business.place_id,
        submission_id=f"sub-{rid}",
        reviewer_phone_hash="abc123",
        reviewer_display_name=name,
        reviewer_country=country,
        extraction=ReviewExtraction(
            business=business,
            business_name_as_said="amala place",
            good=good if good is not None else ["Amala was soft and hot", "Plenty assorted meat"],
            improve=["Queue"],
            recommend=recommend,
            category="street_food",
            overall_sentiment="positive",
            one_line_summary=summary,
        ),
        created_at=created_at,
        status=status,
    )


# ------------------------------------------------------------------- window
def test_default_window_is_seven_days():
    now = datetime(2026, 10, 27, 9, 30, tzinfo=UTC)
    w = default_window(now)
    assert w == Window("2026-10-20T09:30:00Z", "2026-10-27T09:30:00Z")


def test_window_from_dates_and_bounds():
    w = window_from_dates("2026-10-18", "2026-10-27")
    assert w.since == "2026-10-18T00:00:00Z" and w.until == "2026-10-27T00:00:00Z"
    assert in_window("2026-10-18T00:00:00Z", w)  # inclusive start
    assert in_window("2026-10-26T23:59:59Z", w)
    assert not in_window("2026-10-27T00:00:00Z", w)  # exclusive end
    assert window_from_dates("2026-10-18", None).until == "2026-10-25T00:00:00Z"
    assert window_from_dates(None, "2026-10-27").since == "2026-10-20T00:00:00Z"


def test_window_label():
    assert window_label(window_from_dates("2026-10-20", "2026-10-27")) == "20 to 26 Oct 2026"
    assert window_label(window_from_dates("2026-10-28", "2026-11-04")) == "28 Oct to 3 Nov 2026"
    assert (
        window_label(window_from_dates("2026-12-29", "2027-01-05")) == "29 Dec 2026 to 4 Jan 2027"
    )


# --------------------------------------------------------------- eligibility
def test_eligibility_reasons():
    assert eligible(review()) == (True, "")
    assert eligible(review(status="hidden"))[1] == "hidden"
    assert eligible(review(), exclude={"r1"})[1] == "excluded"
    assert eligible(review(summary="Nice."))[1] == "summary too short"
    demo = review(
        "demo-afefedemo01", business=PLACE.model_copy(update={"place_id": "afefe:demo-x"})
    )
    assert eligible(demo)[1] == "demo"
    assert eligible(demo, include_demo=True)[0]


def test_short_summary_falls_back_to_first_good_item():
    r = review(summary="", good=["The jollof was smoky and the plantain perfectly caramelised"])
    assert eligible(r)[0]
    assert to_candidate(r).summary.startswith("The jollof")


# --------------------------------------------------------------- attribution
def test_first_name_rules():
    assert first_name("Tola Adeyemi") == "Tola"
    assert first_name("  chidi  ") == "chidi"
    assert first_name(None) == ANONYMOUS
    assert first_name("") == ANONYMOUS
    assert first_name("+2348031234567") == ANONYMOUS  # phone-shaped name is redacted, never shown
    assert first_name("2348031234567 Ade") == ANONYMOUS


def test_candidate_carries_no_identifier():
    c = to_candidate(review())
    assert c.reviewer_first_name == "Tola" and c.reviewer_country == "NG"
    assert "abc123" not in c.model_dump_json()
    assert "phone" not in c.model_dump_json()


# ----------------------------------------------------------------- selection
def test_select_newest_first_one_per_business_capped():
    other = PLACE.model_copy(
        update={"place_id": "ChIJ-accra-1", "name": "Osu Fade", "city": "Accra"}
    )
    reviews = [
        review("a", created_at="2026-10-21T10:00:00Z"),
        review("b", created_at="2026-10-23T10:00:00Z"),  # same business, newer -> wins
        review("c", created_at="2026-10-22T10:00:00Z", business=other),
        review("old", created_at="2026-10-10T10:00:00Z", business=other),
        review("hid", created_at="2026-10-24T10:00:00Z", status="hidden"),
    ]
    w = window_from_dates("2026-10-18", "2026-10-27")
    picks, skipped = select_candidates(reviews, w, max_picks=6)
    assert [c.review_id for c in picks] == ["b", "c"]
    assert dict(skipped) == {
        "a": "same business already picked",
        "old": "outside window",
        "hid": "hidden",
    }
    picks, _ = select_candidates(reviews, w, max_picks=1)
    assert [c.review_id for c in picks] == ["b"]


def test_select_with_explicit_pick_keeps_order_and_reports_unknown():
    reviews = [review("a"), review("b", created_at="2026-10-22T10:00:00Z")]
    w = window_from_dates("2026-10-18", "2026-10-27")
    picks, skipped = select_candidates(reviews, w, pick=["a", "b", "zzz"])
    assert [c.review_id for c in picks] == ["a", "b"]  # same business allowed when hand-picked
    assert ("zzz", "not an eligible review in this window") in skipped


# ------------------------------------------------------------------- caption
def _cand(i: int, summary: str, city: str = "Lagos", cc: str | None = "NG") -> Candidate:
    return Candidate(
        review_id=f"r{i}",
        business_id=f"b{i}",
        business_name=f"Business {i}",
        city=city,
        country="NG",
        category="restaurant",
        reviewer_first_name="Tola",
        reviewer_country=cc,
        recommend="yes",
        sentiment="positive",
        summary=summary,
        good=["Good thing one", "Good thing two"],
        created_at="2026-10-21T12:00:00Z",
    )


def test_caption_content_and_limits():
    w = window_from_dates("2026-10-20", "2026-10-27")
    picks = [
        _cand(1, "Great jollof.", "Lagos"),
        _cand(2, "Fine coffee.", "Kigali", "RW"),
        _cand(3, "Ok", "Accra", None),
    ]
    text = cap.build_caption(picks, w, wa_number="+234 800 000 0000", hook="Hello week.")
    cap.assert_caption_ok(text)
    assert text.startswith("Hello week.\n\n")
    assert "🇳🇬 Business 1, Lagos: “Great jollof.”" in text
    assert "🇷🇼 Business 2, Kigali" in text
    assert "\nBusiness 3, Accra: “Ok”" in text  # no flag when the country is unknown
    assert "+234 800 000 0000" in text and "afefehub.com" in text
    assert text.rstrip().endswith("#lagos #kigali #accra")
    assert cap.count_hashtags(text) == 8


def test_caption_shrinks_quotes_to_fit_and_rejects_too_many_hashtags():
    w = window_from_dates("2026-10-20", "2026-10-27")
    long = "A very long and winding summary about the meal " * 12
    picks = [_cand(i, long) for i in range(6)]
    text = cap.build_caption(picks, w, wa_number="")
    assert len(text) <= cap.MAX_CAPTION_CHARS
    assert "…" in text
    with pytest.raises(ValueError):
        cap.assert_caption_ok(" ".join(f"#t{i}" for i in range(31)))


# --------------------------------------------------------------------- flags
def test_flag_helpers_offline(tmp_path):
    assert flag_emoji("ng") == "🇳🇬" and flag_emoji(None) == "" and flag_emoji("X1") == ""
    assert twemoji_name("NG") == "1f1f3-1f1ec"
    assert flag_image(None, 64, tmp_path, fetch=False) is None
    chip = flag_image("KE", 64, tmp_path, fetch=False, font_path=FONTS["bold"])
    assert chip.size == (64, 64) and chip.mode == "RGBA"
    assert chip_fallback("GH", 40).getpixel((20, 20))[3] == 255  # opaque ink in the middle
    assert not list(tmp_path.iterdir())  # nothing fetched or cached


# ------------------------------------------------------------------- render
def test_category_label():
    assert category_label("street_food") == "Street food"
    assert category_label("salon_barber") == "Salon & barber"
    assert category_label("restaurant") == "Restaurant"


def test_render_carousel_offline(tmp_path):
    w = window_from_dates("2026-10-20", "2026-10-27")
    picks = [
        _cand(1, "Proper Surulere amala worth the queue."),
        _cand(2, "An extremely long summary " * 14, "Nairobi", None),  # shrink-to-fit, no flag
        _cand(3, "Short and sweet, would go back.", "Accra", "GH"),
    ]
    picks[2].good = []
    paths = render_carousel(picks, w, tmp_path, wa_number="+234 800 000 0000", flag_fetch=False)
    assert [p.name for p in paths] == [f"slide-{i:02d}.jpg" for i in range(1, 6)]
    for p in paths:
        with Image.open(p) as im:
            assert im.format == "JPEG" and im.mode == "RGB" and im.size == (W, H)
        assert p.stat().st_size < 1_000_000
    assert (tmp_path / "preview.png").exists()
    with Image.open(paths[1]) as im:  # a review slide: yellow field, white card
        assert im.getpixel((20, 20))[:3] == (255, 199, 44)
        assert im.getpixel((W // 2, H // 2))[:3] == (255, 255, 255)


# ------------------------------------------------------------------ ranking
import json  # noqa: E402

from app.social import rank as rk  # noqa: E402
from app.social.fetch_week import fetch_week_reviews  # noqa: E402
from app.store import dynamo  # noqa: E402
from tests.fakes import ScriptedChat, reply  # noqa: E402


def _pool() -> list[Candidate]:
    c1 = _cand(1, "Proper Surulere amala worth the twenty-minute queue.", "Lagos", "NG")
    c2 = _cand(2, "Kigali's best spot to work over a serious pour-over.", "Kigali", "RW")
    c2.category = "cafe"
    c3 = _cand(3, "Great choma, terrible timing if there is a match on.", "Nairobi", "KE")
    c3.recommend, c3.sentiment = "maybe", "mixed"
    c4 = _cand(4, "Second review of business one, also very nice indeed.", "Lagos", "NG")
    c4.business_id = "b1"
    c4.created_at = "2026-10-25T12:00:00Z"
    return [c1, c2, c3, c4]


def test_parse_model_picks_validates():
    pool = _pool()
    raw = json.dumps(
        {
            "picks": [
                {"review_id": "r2", "reason": "specific and quotable"},
                {"review_id": "r2", "reason": "dup"},
                {"review_id": "r1", "reason": "x" * 300},
                {"review_id": "r4", "reason": "same business as r1"},
                {"review_id": "nope"},
                "r3",
            ],
            "hook": "Pour-overs, amala and choma: this week across three cities. #tag",
        }
    )
    picks, hook = rk.parse_model_picks(raw, pool, max_picks=5)
    assert [p.review_id for p in picks] == ["r2", "r1", "r3"]
    assert len(picks[1].reason) == rk.MAX_REASON_CHARS
    assert hook == "Pour-overs, amala and choma: this week across three cities."
    picks, _ = rk.parse_model_picks(raw, pool, max_picks=2)
    assert [p.review_id for p in picks] == ["r2", "r1"]
    assert rk.parse_model_picks('```json\n{"picks": ["r3"]}\n```', pool, 5)[0][0].review_id == "r3"
    assert rk.parse_model_picks("not json at all", pool, 5) == ([], "")


def test_rank_with_model_records_reasons_hook_and_call_shape():
    pool = _pool()
    chat = ScriptedChat(
        [
            reply(
                json.dumps(
                    {
                        "picks": [
                            {"review_id": "r3", "reason": "spicy"},
                            {"review_id": "r2", "reason": "crisp"},
                            {"review_id": "r1", "reason": "classic"},
                        ],
                        "hook": "Three cities, three plates.",
                    }
                )
            )
        ]
    )
    res = rk.rank(pool, max_picks=5, min_picks=3, chat=chat)
    assert [c.review_id for c in res.picks] == ["r3", "r2", "r1"]
    assert res.reasons["r3"] == "spicy" and res.hook == "Three cities, three plates."
    assert res.model == "muse-spark-1.3"
    call = chat.calls[0]
    assert call["response_format"] == {"type": "json_object"}
    assert call["reasoning_effort"] == "minimal"
    sent = json.loads(call["messages"][1]["content"])
    assert sent["max_picks"] == 5 and {c["id"] for c in sent["candidates"]} == {
        "r1",
        "r2",
        "r3",
        "r4",
    }
    assert "phone" not in call["messages"][1]["content"]


def test_rank_tops_up_and_falls_back_to_heuristic():
    pool = _pool()
    # model returns one usable pick: heuristic fills to min_picks without repeating a business
    chat = ScriptedChat([reply(json.dumps({"picks": [{"review_id": "r4", "reason": "ok"}]}))])
    res = rk.rank(pool, max_picks=5, min_picks=3, chat=chat)
    ids = [c.review_id for c in res.picks]
    assert ids[0] == "r4" and len(ids) == 3 and "r1" not in ids  # r1 shares r4's business
    assert res.reasons["r2"] == "heuristic top-up" and res.model == "muse-spark-1.3"
    # garbage from the model: heuristic entirely
    res = rk.rank(pool, max_picks=5, min_picks=3, chat=ScriptedChat([reply("nope")]))
    assert res.model == "heuristic" and len(res.picks) == 3

    # the call raising is handled too
    def boom(*a, **k):
        raise RuntimeError("api down")

    res = rk.rank(pool, max_picks=5, min_picks=3, chat=boom)
    assert res.model == "heuristic" and len(res.picks) == 3
    assert rk.rank([], chat=boom).picks == []


def test_heuristic_is_deterministic_and_diverse():
    pool = _pool()
    a = rk.heuristic_order(pool, 5)
    b = rk.heuristic_order(list(reversed(pool)), 5)
    assert [c.review_id for c in a] == [c.review_id for c in b]
    ids = [c.review_id for c in a]
    assert len(ids) == 3 and len({c.business_id for c in a}) == 3
    assert ids[0] in {"r1", "r2", "r4"}  # a recommend-yes, positive review leads
    assert a[0].recommend == "yes" and a[-1].review_id == "r3"  # the mixed one goes last
    # the second pick brings a new country or category rather than another Lagos street-food
    assert (a[1].reviewer_country != a[0].reviewer_country) or (a[1].category != a[0].category)


def test_picks_roundtrip(tmp_path):
    pool = _pool()[:2]
    p = rk.Picks(
        window={"since": "2026-10-20T00:00:00Z", "until": "2026-10-27T00:00:00Z"},
        model="manual",
        picks=[rk.Pick(review_id=c.review_id, reason="r") for c in pool],
        candidates=pool,
    )
    path = rk.write_picks(p, tmp_path / "picks.json")
    back = rk.read_picks(path)
    assert back.candidates == pool and back.generated_at == p.generated_at


# ------------------------------------------------------------ dynamo + fetch
class FakeTable:
    """Records query/scan kwargs and serves pre-baked pages (with LastEvaluatedKey)."""

    def __init__(self, pages: dict[str, list[list[dict]]]):
        self.pages = pages  # keyed by the partition value used in the call
        self.calls: list[dict] = []

    def _serve(self, key, kwargs):
        self.calls.append(kwargs)
        pages = self.pages.get(key, [[]])
        idx = kwargs.get("ExclusiveStartKey", {}).get("page", 0)
        out = {"Items": pages[idx]}
        if idx + 1 < len(pages):
            out["LastEvaluatedKey"] = {"page": idx + 1}
        return out

    def query(self, **kwargs):
        return self._serve(kwargs["ExpressionAttributeValues"][":p"], kwargs)

    def scan(self, **kwargs):
        return self._serve("scan", kwargs)


def _item(r: Review) -> dict:
    return {
        "PK": f"BIZ#{r.business_id}",
        "SK": f"REV#{r.created_at}#{r.review_id}",
        **json.loads(r.model_dump_json(exclude_none=True)),
    }


def test_list_reviews_between_paginates_and_bounds(monkeypatch):
    r_in1 = review("a", created_at="2026-10-21T10:00:00Z")
    r_in2 = review("b", created_at="2026-10-26T23:59:59Z")
    r_edge = review("c", created_at="2026-10-27T00:00:00Z")  # == until: excluded
    table = FakeTable({f"BIZ#{PLACE.place_id}": [[_item(r_in2)], [_item(r_in1), _item(r_edge)]]})
    monkeypatch.setattr(dynamo, "_table", lambda: table)
    got = dynamo.list_reviews_between(
        PLACE.place_id, "2026-10-20T00:00:00Z", "2026-10-27T00:00:00Z"
    )
    assert [r.review_id for r in got] == ["b", "a"]
    kw = table.calls[0]
    assert "BETWEEN" in kw["KeyConditionExpression"] and kw["ScanIndexForward"] is False
    assert kw["ExpressionAttributeValues"][":lo"] == "REV#2026-10-20T00:00:00Z"
    assert "ExclusiveStartKey" in table.calls[1]


def test_list_businesses_updated_since_queries_every_category(monkeypatch):
    biz = {
        "business_id": PLACE.place_id,
        "name": PLACE.name,
        "formatted_address": "x",
        "country": "NG",
        "category": "street_food",
        "updated_at": "2026-10-25T00:00:00Z",
    }
    table = FakeTable({"CAT#street_food": [[biz]]})
    monkeypatch.setattr(dynamo, "_table", lambda: table)
    got = dynamo.list_businesses_updated_since("2026-10-20T00:00:00Z")
    assert [b.business_id for b in got] == [PLACE.place_id]
    from app.models import CATEGORIES

    assert len(table.calls) == len(CATEGORIES)
    assert all(
        c["IndexName"] == "GSI1" and ":s" in c["ExpressionAttributeValues"] for c in table.calls
    )
    assert table.calls[0]["ExpressionAttributeValues"][":s"] == "BIZ#2026-10-20T00:00:00Z"


def test_fetch_week_reviews_joins_businesses_and_windows(monkeypatch):
    from app.models import Business

    other = PLACE.model_copy(
        update={"place_id": "ChIJ-accra-1", "name": "Osu Fade", "city": "Accra"}
    )
    monkeypatch.setattr(
        dynamo,
        "list_businesses_updated_since",
        lambda since: [
            Business(business_id=PLACE.place_id, name="A", formatted_address="x", country="NG"),
            Business(business_id=other.place_id, name="B", formatted_address="y", country="GH"),
        ],
    )
    per_biz = {
        PLACE.place_id: [review("a", created_at="2026-10-21T10:00:00Z")],
        other.place_id: [
            review("c", created_at="2026-10-22T10:00:00Z", business=other),
            review("old", created_at="2026-10-01T10:00:00Z", business=other),
        ],
    }
    monkeypatch.setattr(dynamo, "list_reviews_between", lambda bid, s, u: per_biz[bid])
    w = window_from_dates("2026-10-18", "2026-10-27")
    got = fetch_week_reviews(w)
    assert [r.review_id for r in got] == ["c", "a"]  # newest first, 'old' filtered by the window
    monkeypatch.setattr(dynamo, "scan_reviews_between", lambda s, u: [review("z")])
    assert [r.review_id for r in fetch_week_reviews(w, scan=True)] == ["z"]


# --------------------------------------------------------------- instagram
import httpx  # noqa: E402
import respx  # noqa: E402

from app.social import instagram as ig  # noqa: E402

G = "https://graph.facebook.com/v21.0"


def _client() -> ig.InstagramClient:
    return ig.InstagramClient("1789", "tok", api_version="v21.0")


def test_client_requires_credentials(monkeypatch):
    with pytest.raises(ig.InstagramPublishError):
        ig.InstagramClient("", "tok")
    from app.config import Settings

    with pytest.raises(ig.InstagramPublishError):
        ig.client_from_settings(Settings(ig_user_id="1", ig_access_token=""))
    c = ig.client_from_settings(
        Settings(ig_user_id="1", ig_access_token="t", ig_api_base="https://graph.instagram.com/")
    )
    assert c.base == "https://graph.instagram.com/v21.0"


@respx.mock
def test_preflight_reads_account_and_quota():
    respx.get(f"{G}/1789").mock(
        return_value=httpx.Response(
            200, json={"id": "1789", "username": "afefehub", "name": "Afefehub"}
        )
    )
    respx.get(f"{G}/1789/content_publishing_limit").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"quota_usage": 3, "config": {"quota_total": 50, "quota_duration": 86400}}]
            },
        )
    )
    c = _client()
    assert c.me()["username"] == "afefehub"
    assert c.publishing_limit()["quota_usage"] == 3
    req = respx.calls.last.request
    assert req.headers["Authorization"] == "Bearer tok"
    assert req.url.params["fields"] == "quota_usage,config"


@respx.mock
def test_publish_carousel_happy_path():
    media = respx.post(f"{G}/1789/media").mock(
        side_effect=[
            httpx.Response(200, json={"id": "c1"}),
            httpx.Response(200, json={"id": "c2"}),
            httpx.Response(200, json={"id": "car"}),
        ]
    )
    respx.get(f"{G}/c1").mock(return_value=httpx.Response(200, json={"status_code": "FINISHED"}))
    respx.get(f"{G}/c2").mock(return_value=httpx.Response(200, json={"status_code": "FINISHED"}))
    respx.get(f"{G}/car").mock(
        side_effect=[
            httpx.Response(200, json={"status_code": "IN_PROGRESS", "status": "..."}),
            httpx.Response(200, json={"status_code": "FINISHED"}),
        ]
    )
    pub = respx.post(f"{G}/1789/media_publish").mock(
        return_value=httpx.Response(200, json={"id": "m9"})
    )
    respx.get(f"{G}/m9").mock(
        return_value=httpx.Response(200, json={"permalink": "https://www.instagram.com/p/XYZ/"})
    )
    slept: list[float] = []
    said: list[str] = []
    media_id, link = ig.publish_carousel(
        _client(),
        ["https://s3/a.jpg", "https://s3/b.jpg"],
        "Hello week",
        say=said.append,
        sleep=slept.append,
    )
    assert (media_id, link) == ("m9", "https://www.instagram.com/p/XYZ/")
    bodies = [dict(httpx.QueryParams(c.request.content.decode())) for c in media.calls]
    assert bodies[0] == {"image_url": "https://s3/a.jpg", "is_carousel_item": "true"}
    assert bodies[2] == {"media_type": "CAROUSEL", "children": "c1,c2", "caption": "Hello week"}
    assert dict(httpx.QueryParams(pub.calls[0].request.content.decode())) == {"creation_id": "car"}
    assert slept == [5]  # one IN_PROGRESS poll on the carousel, no real sleeping
    assert len(said) == 3


@respx.mock
def test_publish_errors_are_reported_not_retried():
    respx.post(f"{G}/1789/media").mock(
        return_value=httpx.Response(
            400,
            json={"error": {"message": "Invalid image", "type": "OAuthException", "code": 9004}},
        )
    )
    with pytest.raises(ig.InstagramPublishError, match="9004: Invalid image"):
        ig.publish_carousel(
            _client(), ["https://s3/a.jpg", "https://s3/b.jpg"], "x", sleep=lambda s: None
        )
    assert len(respx.calls) == 1  # stopped at the first failure


def test_publish_rejects_bad_counts_before_any_http():
    with pytest.raises(ig.InstagramPublishError, match="2 to 10"):
        ig.publish_carousel(_client(), ["one"], "x")
    with pytest.raises(ig.InstagramPublishError, match="2 to 10"):
        _client().create_carousel_container([f"c{i}" for i in range(11)], "x")


@respx.mock
def test_wait_finished_raises_on_error_and_timeout(monkeypatch):
    respx.get(f"{G}/bad").mock(
        return_value=httpx.Response(
            200, json={"status_code": "ERROR", "status": "Media upload failed"}
        )
    )
    with pytest.raises(ig.InstagramPublishError, match="ERROR: Media upload failed"):
        _client().wait_finished("bad", sleep=lambda s: None)

    respx.get(f"{G}/slow").mock(
        return_value=httpx.Response(200, json={"status_code": "IN_PROGRESS"})
    )
    clock = iter([0, 1, 2, 400, 401])
    monkeypatch.setattr(ig.time, "monotonic", lambda: next(clock))
    with pytest.raises(ig.InstagramPublishError, match="still IN_PROGRESS"):
        _client().wait_finished("slow", timeout_s=300, sleep=lambda s: None)


@respx.mock
def test_permalink_failure_after_publish_is_tolerated():
    respx.post(f"{G}/1789/media").mock(
        side_effect=[
            httpx.Response(200, json={"id": "c1"}),
            httpx.Response(200, json={"id": "c2"}),
            httpx.Response(200, json={"id": "car"}),
        ]
    )
    respx.get(url__regex=rf"{G}/(c1|c2|car)\?.*").mock(
        return_value=httpx.Response(200, json={"status_code": "FINISHED"})
    )
    respx.post(f"{G}/1789/media_publish").mock(return_value=httpx.Response(200, json={"id": "m1"}))
    respx.get(f"{G}/m1").mock(return_value=httpx.Response(500, text="oops"))
    assert ig.publish_carousel(_client(), ["u1", "u2"], "c", sleep=lambda s: None) == ("m1", "")


@respx.mock
def test_publish_reel_sends_one_reels_container_then_publishes():
    media = respx.post(f"{G}/1789/media").mock(return_value=httpx.Response(200, json={"id": "rc"}))
    respx.get(f"{G}/rc").mock(
        side_effect=[
            httpx.Response(200, json={"status_code": "IN_PROGRESS"}),
            httpx.Response(200, json={"status_code": "FINISHED"}),
        ]
    )
    pub = respx.post(f"{G}/1789/media_publish").mock(
        return_value=httpx.Response(200, json={"id": "m7"})
    )
    respx.get(f"{G}/m7").mock(
        return_value=httpx.Response(200, json={"permalink": "https://www.instagram.com/reel/R/"})
    )
    slept: list[float] = []
    out = ig.publish_reel(
        _client(), "https://s3/reel.mp4", "Week", cover_url="https://s3/c.jpg", sleep=slept.append
    )
    assert out == ("m7", "https://www.instagram.com/reel/R/")
    body = dict(httpx.QueryParams(media.calls.last.request.content.decode()))
    assert body == {
        "media_type": "REELS",
        "video_url": "https://s3/reel.mp4",
        "caption": "Week",
        "share_to_feed": "true",
        "cover_url": "https://s3/c.jpg",
    }
    assert len(media.calls) == 1 and slept == [10]
    assert dict(httpx.QueryParams(pub.calls.last.request.content.decode())) == {"creation_id": "rc"}


# --------------------------------------------------------------------- reel
import math  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import wave  # noqa: E402
from array import array  # noqa: E402

from app.social import audio as au  # noqa: E402
from app.social import reel as rl  # noqa: E402

needs_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg not installed"
)


def test_candidate_knows_where_the_audio_is():
    r = review()
    r.audio_s3_key = "submissions/sub-r1/voice.m4a"
    c = to_candidate(r)
    assert c.submission_id == "sub-r1"
    assert au.s3_audio_keys(c) == [
        "submissions/sub-r1/voice.m4a",
        "submissions/sub-r1/audio.wav",
        "submissions/sub-r1/voice.ogg",
    ]
    c.audio_s3_key, c.video_s3_key = None, "submissions/sub-r1/source.mp4"
    assert au.s3_audio_keys(c)[0] == "submissions/sub-r1/source.mp4"


def _tone(seconds: float, gaps: tuple[tuple[float, float], ...] = ()) -> bytes:
    n = int(seconds * au.RATE)
    s = array("h", (int(12_000 * math.sin(2 * math.pi * 220 * i / au.RATE)) for i in range(n)))
    for a, b in gaps:
        for i in range(int(a * au.RATE), int(b * au.RATE)):
            s[i] = 0
    return s.tobytes()


def test_peaks_shape_and_silence():
    lv = au.peaks(_tone(2.0, gaps=((0.5, 1.0),)), 40)
    assert len(lv) == 40 and max(lv) == pytest.approx(1.0) and min(lv) >= 0
    assert all(v == 0 for v in lv[11:19]) and all(v > 0.9 for v in lv[:9])
    assert au.peaks(bytes(1000), 10) == [0.0] * 10
    assert au.peaks(b"", 5) == [0.0] * 5


def test_review_scene_waveform_fills_as_it_plays():
    w = window_from_dates("2026-10-20", "2026-10-27")
    base = rl.render_reel_card(_cand(1, "Proper amala."), w, flag=None, site_url="afefehub.com")
    assert base.size == (rl.RW, rl.RH)
    clip = au.Clip("r1", 0, 2000, _tone(2.0))
    sc = rl.ReviewScene(base, clip)
    mid_y = rl.WAVE_Y + rl.WAVE_H // 2
    first_bar_x = sc.x0 + rl.BAR_W // 2
    last_bar_x = sc.x0 + (sc.n_bars - 1) * (rl.BAR_W + rl.BAR_GAP) + rl.BAR_W // 2
    start, end = sc.frame(0.0), sc.frame(2.0)

    def dark(img, x):
        return max(img.getpixel((x, mid_y))) < 40  # ink, not the unplayed grey

    assert not dark(start, first_bar_x)  # nothing played yet
    assert dark(end, first_bar_x) and dark(end, last_bar_x)  # all played at the end
    assert rl.timecode(65.9) == "01:05"


def _wav(path, seconds: float, gaps=((1.0, 1.5),)):
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1), f.setsampwidth(2), f.setframerate(au.RATE)
        f.writeframes(_tone(seconds, gaps=gaps))
    return path


@needs_ffmpeg
def test_make_clip_keeps_the_whole_recording_and_caps_only_past_the_limit(tmp_path):
    c1, c2 = _cand(1, "Proper Surulere amala worth the queue."), _cand(2, "Fine coffee.")
    _wav(tmp_path / "r1.wav", 4.0)
    a, whole = au.first_clip("r1", au.local_sources(c1, tmp_path))
    assert abs(a.duration_ms - 4000) < 50
    assert list(au.local_sources(c2, tmp_path)) == []
    assert (whole.start_ms, whole.end_ms) == (0, a.duration_ms)
    assert abs(whole.duration_s - 4.0) < 0.05
    capped = au.make_clip(a, max_s=2.5)
    assert capped.end_ms == 2500 and abs(capped.duration_s - 2.5) < 0.05
    _wav(tmp_path / "r2.wav", 0.4, gaps=())
    with pytest.raises(au.ReviewAudioError, match="too short"):
        au.first_clip("r2", au.local_sources(c2, tmp_path))


@needs_ffmpeg
def test_first_clip_falls_through_an_unreadable_source(tmp_path):
    (tmp_path / "r1.m4a").write_bytes(b"not audio at all")  # tried first, fails to probe
    _wav(tmp_path / "r1.wav", 2.0)
    src, clip = au.first_clip("r1", au.local_sources(_cand(1, "x" * 30), tmp_path))
    assert src.path.name == "r1.wav" and abs(clip.duration_s - 2.0) < 0.05
    with pytest.raises(au.ReviewAudioError, match="no audio found"):
        au.first_clip("r9", iter(()))
    with pytest.raises(au.ReviewAudioError, match=r"r1\.m4a"):
        au.first_clip("r1", [tmp_path / "r1.m4a"])


def test_s3_sources_skips_missing_keys_and_is_lazy(monkeypatch, tmp_path):
    from botocore.exceptions import ClientError

    from app.store import s3

    c = _cand(1, "x" * 30)
    c.submission_id, c.audio_s3_key = "sub1", "submissions/sub1/voice.m4a"
    tried: list[str] = []

    def download(key, dest):
        tried.append(key)
        if key.endswith(".m4a"):
            raise ClientError({"Error": {"Code": "404"}}, "GetObject")
        dest.write_bytes(b"x")
        return dest

    monkeypatch.setattr(s3, "download_file", download)
    it = au.s3_sources(c, tmp_path)
    assert next(it).name == "r1.wav"  # m4a missing, the transcription WAV next
    assert tried == ["submissions/sub1/voice.m4a", "submissions/sub1/audio.wav"]
    assert next(it).name == "r1.ogg"  # only fetched when the WAV is not good enough


@needs_ffmpeg
def test_render_review_reel_end_to_end(tmp_path):
    c1 = _cand(1, "Proper Surulere amala worth the queue.")
    _wav(tmp_path / "r1.wav", 4.0)
    _, clip = au.first_clip("r1", au.local_sources(c1, tmp_path))
    w = window_from_dates("2026-10-20", "2026-10-27")
    res = rl.render_review_reel(c1, clip, w, tmp_path / "out", flag_fetch=False)
    want = clip.duration_s + rl.TAIL_S + rl.CTA_S
    assert abs(res.duration_s - want) < 0.1
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,codec_name,width,height,sample_rate:format=duration",
         "-of", "json", str(res.video)],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    info = json.loads(probe.stdout)
    streams = {s["codec_type"]: s for s in info["streams"]}
    assert streams["video"]["codec_name"] == "h264"
    assert (streams["video"]["width"], streams["video"]["height"]) == (1080, 1920)
    assert streams["audio"]["codec_name"] == "aac" and streams["audio"]["sample_rate"] == "48000"
    assert abs(float(info["format"]["duration"]) - want) < 0.15
    with Image.open(res.cover) as im:  # the card itself is the cover, not a separate title card
        assert im.size == (1080, 1920) and im.format == "JPEG"
        assert im.getpixel((rl.RW // 2, rl.INNER_TOP + 300))[:3] == (255, 255, 255)
    assert res.preview.exists()
    with pytest.raises(ValueError):
        rl.render_review_reel(c1, au.Clip("r1", 0, 0, b""), w, tmp_path / "bad")


def test_review_caption_is_first_name_flag_and_the_review():
    w = window_from_dates("2026-10-20", "2026-10-27")
    c = to_candidate(review())
    text = cap.build_review_caption(c, w, wa_number="+234 800 000 0000")
    lines = text.splitlines()
    assert lines[0] == "🇳🇬 Tola on Amala Corner Surulere, Lagos"
    assert "“Proper Surulere amala worth the twenty-minute queue.”" in text
    assert "+ Amala was soft and hot" in text
    assert "Reviews of the week (20 to 26 Oct 2026)" in text
    assert "+234 800 000 0000" in text and "#lagos" in text
    assert "abc123" not in text and "Adeyemi" not in text  # no hash, no surname
    cap.assert_caption_ok(text)
    long = c.model_copy(update={"summary": "word " * 900, "good": ["x" * 300] * 3})
    assert len(cap.build_review_caption(long, w)) <= cap.MAX_CAPTION_CHARS


# ------------------------------------------------------------- publishing a week
from pathlib import Path  # noqa: E402

from app.social import weekly_publish as wp  # noqa: E402


class FakeIG:
    """Stands in for publish_carousel / publish_reel; fails the reels named in ``fail``."""

    def __init__(self, fail=()):
        self.fail, self.calls = set(fail), []

    def carousel(self, client, urls, caption, **kw):
        self.calls.append(("carousel", len(urls)))
        return "car1", "https://ig/p/C/"

    def reel(self, client, video_url, caption, *, cover_url="", **kw):
        self.calls.append(("reel", video_url))
        if any(f in video_url for f in self.fail):
            raise ig.InstagramPublishError("boom")
        return f"m-{video_url}", f"https://ig/reel/{video_url}/"


def _jobs(tmp_path, *ids):
    return [
        wp.ReelJob(i, f"Biz {i}", tmp_path / f"{i}.mp4", tmp_path / f"{i}.jpg", f"cap {i}", 30.0)
        for i in ids
    ]


def _run(monkeypatch, fake, record, reels, slides=("s1.jpg", "s2.jpg")):
    monkeypatch.setattr(wp, "publish_carousel", fake.carousel)
    monkeypatch.setattr(wp, "publish_reel", fake.reel)
    saved: list[dict] = []
    ok = wp.publish_week(
        None, record, run_id="w1", slides=[Path(s) for s in slides], caption="c",
        reels=reels, upload=lambda p, key, ct: key,
        save=lambda r: saved.append(json.loads(json.dumps(r))),
        say=lambda m: None,
    )  # fmt: skip
    return ok, saved


def test_publish_week_posts_carousel_then_each_reel_and_records_each(monkeypatch, tmp_path):
    fake = FakeIG()
    rec = wp.new_record("w1", "afefehub")
    ok, saved = _run(monkeypatch, fake, rec, _jobs(tmp_path, "r1", "r2"))
    assert ok
    assert fake.calls == [
        ("carousel", 2),
        ("reel", "social/weekly/w1/reels/r1.mp4"),
        ("reel", "social/weekly/w1/reels/r2.mp4"),
    ]
    assert len(saved) == 3  # written after every post, not only at the end
    assert saved[0]["carousel"]["media_id"] == "car1" and saved[0]["reels"] == []
    assert [r["review_id"] for r in saved[-1]["reels"]] == ["r1", "r2"]


def test_publish_week_carries_on_past_a_failed_reel_and_a_rerun_finishes(monkeypatch, tmp_path):
    jobs = _jobs(tmp_path, "r1", "r2", "r3")
    rec = wp.new_record("w1", "afefehub")
    ok, _ = _run(monkeypatch, FakeIG(fail={"r2"}), rec, jobs)
    assert not ok and [r["review_id"] for r in rec["reels"]] == ["r1", "r3"]

    again = FakeIG()
    rec2 = wp.new_record("w1", "afefehub", json.loads(json.dumps(rec)))
    assert wp.pending(rec2, jobs) == (False, [jobs[1]])
    ok, _ = _run(monkeypatch, again, rec2, jobs)
    assert ok and again.calls == [("reel", "social/weekly/w1/reels/r2.mp4")]  # nothing twice
    assert [r["review_id"] for r in rec2["reels"]] == ["r1", "r3", "r2"]


def test_publish_week_stops_when_the_carousel_fails(monkeypatch, tmp_path):
    def bad_carousel(*a, **kw):
        raise ig.InstagramPublishError("nope")

    fake = FakeIG()
    monkeypatch.setattr(wp, "publish_carousel", bad_carousel)
    monkeypatch.setattr(wp, "publish_reel", fake.reel)
    rec = wp.new_record("w1", "afefehub")
    ok = wp.publish_week(
        None, rec, run_id="w1", slides=[Path("s1.jpg")], caption="c",
        reels=_jobs(tmp_path, "r1"), upload=lambda p, k, ct: k, save=lambda r: None,
        say=lambda m: None,
    )  # fmt: skip
    assert not ok and fake.calls == [] and rec["carousel"] is None


def test_merge_records_counts_a_post_done_if_any_copy_lists_it(tmp_path):
    local = wp.new_record("w1", "afefehub")
    local["reels"] = [{"review_id": "r1", "media_id": "m1"}]
    remote = wp.new_record("w1", "afefehub")
    remote["carousel"] = {"media_id": "car"}
    remote["reels"] = [{"review_id": "r1", "media_id": "m1"}, {"review_id": "r2", "media_id": "m2"}]
    merged = wp.merge_records(local, remote)
    assert merged["carousel"] == {"media_id": "car"}
    assert [r["review_id"] for r in merged["reels"]] == ["r1", "r2"]
    jobs = _jobs(tmp_path, "r1", "r2", "r3")
    assert wp.pending(merged, jobs) == (False, [jobs[2]])
    # a fresh machine with no local file still sees what S3 recorded
    assert wp.pending(wp.merge_records(wp.new_record("w1", "a"), remote), jobs)[1] == [jobs[2]]


def test_new_record_reads_older_single_post_records():
    old_reel = {"media_id": "m1", "permalink": "p", "format": "reel", "run_id": "w1"}
    rec = wp.new_record("w1", "afefehub", old_reel)
    assert rec["carousel"] is None and rec["earlier"] == [old_reel]  # the round-up Reel test
    old_car = {"media_id": "m2", "permalink": "p2", "published_at": "t", "slides": ["a"]}
    assert wp.new_record("w1", "a", old_car)["carousel"]["media_id"] == "m2"
