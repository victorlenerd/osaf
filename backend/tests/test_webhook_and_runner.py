import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.models import QA, Conversation, Review, Submission, SubmissionState, Transcript
from app.pipeline import runner


def _payload(
    text: str, wamid: str = "wamid.1", phone: str = "2348012345678", sent_to: str = "111222333"
) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "2348000000000",
                                "phone_number_id": sent_to,
                            },
                            "contacts": [{"wa_id": phone, "profile": {"name": "Ada"}}],
                            "messages": [
                                {"from": phone, "id": wamid, "type": "text", "text": {"body": text}}
                            ],
                        }
                    }
                ]
            }
        ],
    }


@pytest.fixture
def client(monkeypatch):
    from app.main import app

    seen: set[str] = set()
    monkeypatch.setattr(
        "app.whatsapp.webhook.dynamo.claim_wa_message",
        lambda w: seen.add(w) is None if w not in seen else False,
    )
    calls: list = []
    monkeypatch.setattr("app.whatsapp.webhook.process_inbound", lambda *a: calls.append(a))
    c = TestClient(app)
    c.calls = calls  # type: ignore[attr-defined]
    return c


def test_verify_challenge(client):
    get_settings().whatsapp_verify_token = "tok"
    r = client.get(
        "/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "tok", "hub.challenge": "123"},
    )
    assert r.status_code == 200 and r.text == "123"
    assert (
        client.get(
            "/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "x"}
        ).status_code
        == 403
    )


def test_signature_and_dedupe(client):
    get_settings().meta_app_secret = "secret"
    body = json.dumps(_payload("hello")).encode()
    sig = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert (
        client.post(
            "/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": "sha256=bad"}
        ).status_code
        == 403
    )
    r = client.post("/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": sig})
    assert r.json()["queued"] == 1
    r = client.post("/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": sig})
    assert r.json()["queued"] == 0  # duplicate wamid ignored
    assert client.calls[0][0] == "2348012345678" and client.calls[0][2] == "Ada"
    assert client.calls[0][3] == "111222333"  # the business number it arrived on
    get_settings().meta_app_secret = ""


def test_webhook_without_metadata_still_queues(client):
    get_settings().meta_app_secret = "secret"
    payload = _payload("hello", wamid="wamid.nometa")
    del payload["entry"][0]["changes"][0]["value"]["metadata"]
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    r = client.post("/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": sig})
    assert r.json()["queued"] == 1 and client.calls[0][3] is None
    get_settings().meta_app_secret = ""


class FakeStore:
    def __init__(self):
        self.convs: dict[str, Conversation] = {}
        self.subs: dict[str, Submission] = {}
        self.reviews: list[Review] = []
        self.points: dict[str, int] = {}

    def get_conversation(self, phone):
        return self.convs.get(phone)

    def put_conversation(self, c):
        self.convs[c.phone] = c

    def get_submission(self, sid):
        return self.subs.get(sid)

    def put_submission(self, s):
        self.subs[s.submission_id] = s

    def list_reviews_by_reviewer_since(self, reviewer_hash, since_iso, limit=50):
        hits = [
            r
            for r in self.reviews
            if r.reviewer_phone_hash == reviewer_hash and r.created_at >= since_iso
        ]
        return sorted(hits, key=lambda r: r.created_at)[:limit]

    def add_points(self, phone, n):
        self.points[phone] = self.points.get(phone, 0) + n
        return self.points[phone]

    def clear_deletion_request(self, phone):
        if phone in self.convs:  # conditional on the item existing, like the real one
            self.convs[phone].deletion_requested_at = None

    def clear_erasure_marker(self, phone):
        if phone in self.convs:
            self.convs[phone].erasure_started_at = None

    def set_erasure_businesses(self, phone, ids):
        if phone in self.convs:
            self.convs[phone].erasure_businesses = ids

    def get_points(self, phone):
        return self.points.get(phone, 0)


def _published_review(store: FakeStore, phone: str, days_ago: float) -> Review:
    """Seed a review this phone published `days_ago` days back."""
    from datetime import UTC, datetime, timedelta

    from app.models import PlaceRef, ReviewExtraction

    created = (datetime.now(UTC) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = Review(
        review_id=f"r{len(store.reviews)}",
        business_id="x",
        submission_id=f"s{len(store.reviews)}",
        reviewer_phone_hash=runner.quota.phone_hash(phone),
        extraction=ReviewExtraction(
            business=PlaceRef(place_id="x", name="n", formatted_address="a", country="NG"),
            business_name_as_said="n",
        ),
        created_at=created,
    )
    store.reviews.append(r)
    return r


@pytest.fixture
def world(monkeypatch):
    store = FakeStore()
    sent: list[tuple[str, str]] = []
    events: list[str] = []
    monkeypatch.setattr(runner, "dynamo", store)
    monkeypatch.setattr(runner.quota, "dynamo", store)
    monkeypatch.setattr(runner.wa, "send_text", lambda to, body, **k: sent.append((to, body)))
    monkeypatch.setattr(
        runner,
        "_run_pipeline",
        lambda sub, conv, **k: events.append(f"pipeline:{sub.reel_shortcode}"),
    )
    monkeypatch.setattr(
        runner,
        "_extract_and_route",
        lambda sub, conv, latest_answer: events.append(f"extract:{latest_answer}"),
    )
    monkeypatch.setattr(
        runner.publish, "publish_submission", lambda sub, conv: events.append("publish")
    )
    # Discovery never reaches the model API here: the intent check reads every message as an
    # answer, and a discovery turn is recorded instead of run, unless a test says otherwise.
    monkeypatch.setattr(runner.discover, "classify_intent", lambda text, q: "answer")

    def fake_turn(conv, text):
        events.append(f"discover:{text}")
        return runner.discover.DiscoveryOutcome(
            message=f"vendors for {text}",
            session=runner.discover.DiscoverySession(last_query=text),
            searched=True,
        )

    monkeypatch.setattr(runner.discover, "run_discovery_turn", fake_turn)
    store.discovery_turns = 0

    def incr(phone):
        store.discovery_turns += 1
        return store.discovery_turns

    store.incr_discovery_count = incr
    return store, sent, events


def _text(body: str) -> dict:
    return {"type": "text", "text": {"body": body}}


def test_greeting_gets_help(world):
    store, sent, events = world
    runner.process_inbound("2348012345678", _text("hello"), "Ada")
    assert "Afefehub" in sent[0][1] and not events


def test_reel_link_starts_pipeline_and_country_from_phone(world):
    store, sent, events = world
    runner.process_inbound(
        "2348012345678", _text("check this https://www.instagram.com/reel/AbC123/?igsh=x"), "Ada"
    )
    assert events == ["pipeline:AbC123"]
    conv = store.convs["2348012345678"]
    assert conv.profile_country == "NG" and conv.display_name == "Ada"
    sub = store.subs[conv.active_submission_id]
    assert sub.reel_url == "https://www.instagram.com/reel/AbC123/"


def test_new_link_abandons_active_submission(world):
    store, sent, events = world
    phone = "2348012345678"
    runner.process_inbound(phone, _text("https://www.instagram.com/reel/one/"))
    first = store.convs[phone].active_submission_id
    store.subs[first].state = SubmissionState.AWAITING_CLARIFICATION
    runner.process_inbound(phone, _text("https://www.instagram.com/reel/two/"))
    assert store.subs[first].state == SubmissionState.ABANDONED
    assert events == ["pipeline:one", "pipeline:two"]


def test_clarification_answer_is_logged_and_routed(world):
    store, sent, events = world
    phone = "2348012345678"
    sub = Submission(
        submission_id="s1",
        phone=phone,
        reel_url="u",
        reel_shortcode="sc",
        state=SubmissionState.AWAITING_CLARIFICATION,
        pending_question="Which city?",
    )
    store.subs["s1"] = sub
    store.convs[phone] = Conversation(phone=phone, active_submission_id="s1")
    runner.process_inbound(phone, _text("Ikeja"))
    assert sub.qa_log == [QA(q="Which city?", a="Ikeja")]
    assert sub.state == SubmissionState.EXTRACTING
    assert events == ["extract:Ikeja"]


def test_confirm_publishes_and_correction_reextracts(world):
    store, sent, events = world
    phone = "2348012345678"
    sub = Submission(
        submission_id="s1",
        phone=phone,
        reel_url="u",
        reel_shortcode="sc",
        state=SubmissionState.CONFIRMING,
        pending_question="Here's what I got",
    )
    store.subs["s1"] = sub
    store.convs[phone] = Conversation(phone=phone, active_submission_id="s1")
    runner.process_inbound(phone, _text("the address is wrong, it's on Opebi road"))
    assert events == ["extract:CORRECTION from reviewer: the address is wrong, it's on Opebi road"]
    sub.state = SubmissionState.CONFIRMING
    runner.process_inbound(phone, _text("ok 👍"))
    assert events[-1] == "publish"


def test_transient_state_says_wait(world):
    store, sent, events = world
    phone = "2348012345678"
    store.subs["s1"] = Submission(
        submission_id="s1",
        phone=phone,
        reel_url="u",
        reel_shortcode="sc",
        state=SubmissionState.TRANSCRIBING,
    )
    store.convs[phone] = Conversation(phone=phone, active_submission_id="s1")
    runner.process_inbound(phone, _text("hello?"))
    assert "Still working" in sent[-1][1] and not events


def test_paused_submission_waits_for_model_key(world):
    store, sent, events = world
    phone = "2348012345678"
    store.subs["s1"] = Submission(
        submission_id="s1",
        phone=phone,
        reel_url="u",
        reel_shortcode="sc",
        state=SubmissionState.PAUSED,
        s3_video_key="submissions/s1/source.mp4",
    )
    store.convs[phone] = Conversation(phone=phone, active_submission_id="s1")
    settings = get_settings()
    settings.model_api_key = ""
    runner.process_inbound(phone, _text("any news?"))
    assert "paused" in sent[-1][1] and not events
    settings.model_api_key = "k"
    try:
        runner.process_inbound(phone, _text("hello again"))
    finally:
        settings.model_api_key = ""
    assert events == ["pipeline:sc"]
    assert store.subs["s1"].state == SubmissionState.DOWNLOADING


REEL = "https://www.instagram.com/reel/AbC123/"
PHONE = "2348012345678"


def test_fourth_review_in_window_is_refused(world):
    store, sent, events = world
    for days in (1, 2, 3):
        _published_review(store, PHONE, days)
    runner.process_inbound(PHONE, _text(REEL), "Ada")
    assert not events and not store.subs
    assert "next slot" in sent[0][1] and "in 4 days" in sent[0][1]


def test_limit_ignores_reviews_outside_window(world):
    store, sent, events = world
    for days in (1, 1, 8):
        _published_review(store, PHONE, days)
    runner.process_inbound(PHONE, _text(REEL), "Ada")
    assert events == ["pipeline:AbC123"]


def test_limit_refusal_keeps_active_submission(world):
    store, sent, events = world
    for days in (1, 2, 3):
        _published_review(store, PHONE, days)
    store.subs["s1"] = Submission(
        submission_id="s1", phone=PHONE, reel_shortcode="old", state=SubmissionState.CONFIRMING
    )
    store.convs[PHONE] = Conversation(phone=PHONE, active_submission_id="s1")
    runner.process_inbound(PHONE, _text(REEL), "Ada")
    assert store.subs["s1"].state == SubmissionState.CONFIRMING and not events
    assert len(sent) == 1 and "dropping" not in sent[0][1]


def test_voice_note_refused_at_limit(voice):
    store, sent, events, heard = voice
    for days in (1, 2, 3):
        _published_review(store, PHONE, days)
    runner.process_inbound(PHONE, _audio("m7"), "Ada")
    assert not events and not store.subs
    assert "next slot" in sent[0][1]


def test_points_command_reports_balance_and_slots(world):
    store, sent, events = world
    store.points[PHONE] = 30
    _published_review(store, PHONE, 1)
    for word in ("Points?", "my points", "balance", "SCORE"):
        runner.process_inbound(PHONE, _text(word), "Ada")
        assert "30 points" in sent[-1][1] and "2 review slots" in sent[-1][1]
    runner.process_inbound(PHONE, _text("I have points"), "Ada")
    assert "Afefehub" in sent[-1][1] and not events


def test_points_command_does_not_consume_clarification(world):
    store, sent, events = world
    store.subs["s1"] = Submission(
        submission_id="s1",
        phone=PHONE,
        reel_shortcode="sc",
        state=SubmissionState.AWAITING_CLARIFICATION,
        pending_question="Which Yaba?",
    )
    store.convs[PHONE] = Conversation(phone=PHONE, active_submission_id="s1")
    runner.process_inbound(PHONE, _text("points"), "Ada")
    sub = store.subs["s1"]
    assert sub.qa_log == [] and sub.state == SubmissionState.AWAITING_CLARIFICATION
    assert not events and "still waiting" in sent[0][1]


def test_help_mentions_limit_and_points(world):
    store, sent, events = world
    runner.process_inbound(PHONE, _text("hello"), "Ada")
    assert "3 reviews a week" in sent[0][1] and "10 points" in sent[0][1]


def test_quota_math_and_humanize(monkeypatch):
    from datetime import UTC, datetime, timedelta

    from app.pipeline import quota

    store = FakeStore()
    monkeypatch.setattr(quota, "dynamo", store)
    now = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
    for days in (6.5, 2, 0.5):
        _published_review(store, PHONE, days)
    oldest = store.reviews[0].created_at
    q = quota.weekly_quota(PHONE, now=datetime.now(UTC))
    assert q.used == 3 and q.remaining == 0 and q.exhausted
    assert q.next_open_at == (quota._parse(oldest) + timedelta(days=7)).strftime(quota.ISO)

    def at(hours: float) -> str:
        return (now + timedelta(hours=hours)).strftime(quota.ISO)

    assert quota.humanize_until(at(5), now) == "in about 5 hours"
    assert quota.humanize_until(at(0.2), now) == "in about 1 hour"
    assert quota.humanize_until(at(24), now) == "tomorrow"
    assert quota.humanize_until(at(26), now) == "in 2 days"
    assert quota.slots_line(quota.WeeklyQuota(used=2, limit=3)) == (
        "You have 1 review slot left this week."
    )


def test_add_points_update_expression(monkeypatch):
    from decimal import Decimal

    from app.store import dynamo

    calls: list[dict] = []

    class T:
        def update_item(self, **kw):
            calls.append(kw)
            return {"Attributes": {"points": Decimal(40)}}

    monkeypatch.setattr(dynamo, "_table", lambda: T())
    total = dynamo.add_points("p", 10)
    assert total == 40 and isinstance(total, int)
    kw = calls[0]
    assert kw["ReturnValues"] == "UPDATED_NEW" and kw["Key"]["SK"] == "POINTS"
    for key in kw["ExpressionAttributeValues"]:
        assert key in kw["UpdateExpression"]


def test_business_upsert_uses_every_expression_value(monkeypatch):
    """DynamoDB rejects UpdateItem when ExpressionAttributeValues has unused keys."""
    import re

    from app.models import PlaceRef, ReviewExtraction
    from app.store import dynamo

    calls: list[dict] = []

    class T:
        def update_item(self, **kw):
            calls.append(kw)

        def get_item(self, **kw):
            return {
                "Item": {"business_id": "x", "name": "n", "formatted_address": "a", "country": "NG"}
            }

    monkeypatch.setattr(dynamo, "_table", lambda: T())
    ext = ReviewExtraction(
        business=PlaceRef(place_id="x", name="n", formatted_address="a", country="NG"),
        business_name_as_said="n",
        keywords=["suya", "Suya ", "yaba"],
        recommend="yes",
    )
    dynamo.upsert_business_on_publish(ext)
    assert len(calls) == 2
    for kw in calls:
        used = set(re.findall(r":[a-z_0-9]+", kw["UpdateExpression"]))
        assert used == set(kw["ExpressionAttributeValues"]), kw["UpdateExpression"]
        used_names = set(re.findall(r"#[a-z_0-9]+", kw["UpdateExpression"]))
        assert used_names == set(kw["ExpressionAttributeNames"])


def test_access_log_redacts_verify_token():
    import logging

    from app.main import RedactVerifyToken

    rec = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/1.1" %d',
        (
            "1.2.3.4:1",
            "GET",
            "/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=s3cret&hub.challenge=1",
            200,
        ),
        None,
    )
    assert RedactVerifyToken().filter(rec)
    assert "s3cret" not in rec.getMessage() and "hub.verify_token=***" in rec.getMessage()


# ----------------------------------------------------------------------- voice notes
def _audio(media_id: str = "m1") -> dict:
    return {"type": "audio", "audio": {"id": media_id, "mime_type": "audio/ogg; codecs=opus"}}


@pytest.fixture
def voice(world, monkeypatch):
    """Voice-note helpers stubbed: `heard` is what the transcriber returns next."""
    store, sent, events = world
    heard = {"text": "Ikeja, the one on Allen Avenue"}
    monkeypatch.setattr(get_settings(), "model_api_key", "k")  # transcription needs the key
    monkeypatch.setattr(runner, "fetch_voice_note", lambda media_id, work: work / "voice.ogg")
    monkeypatch.setattr(runner, "audio_duration", lambda path: heard.get("seconds", 5))
    monkeypatch.setattr(
        runner,
        "transcribe_voice_note",
        lambda note, work, keywords=None: (Transcript(text=heard["text"]), {}),
    )
    return store, sent, events, heard


def test_webhook_queues_audio_messages(client):
    get_settings().meta_app_secret = ""
    payload = _payload("x", wamid="wamid.audio")
    payload["entry"][0]["changes"][0]["value"]["messages"] = [
        {"from": "2348012345678", "id": "wamid.audio", **_audio("m9")}
    ]
    r = client.post("/webhooks/whatsapp", json=payload)
    assert r.json()["queued"] == 1
    assert client.calls[-1][1]["audio"]["id"] == "m9"


def test_voice_answer_is_transcribed_and_routed(voice):
    store, sent, events, heard = voice
    phone = "2348012345678"
    store.subs["s1"] = Submission(
        submission_id="s1",
        phone=phone,
        reel_url="u",
        reel_shortcode="sc",
        state=SubmissionState.AWAITING_CLARIFICATION,
        pending_question="Which branch?",
    )
    store.convs[phone] = Conversation(phone=phone, active_submission_id="s1")
    runner.process_inbound(phone, _audio(), "Ada")
    assert store.subs["s1"].qa_log == [QA(q="Which branch?", a="🎤 Ikeja, the one on Allen Avenue")]
    assert events == ["extract:Ikeja, the one on Allen Avenue"]
    assert any("Listening" in b for _, b in sent)


def test_voice_ok_confirms(voice):
    store, sent, events, heard = voice
    phone = "2348012345678"
    store.subs["s1"] = Submission(
        submission_id="s1",
        phone=phone,
        reel_url="u",
        reel_shortcode="sc",
        state=SubmissionState.CONFIRMING,
        pending_question="Here's what I got",
    )
    store.convs[phone] = Conversation(phone=phone, active_submission_id="s1")
    heard["text"] = "Okay, publish it."
    runner.process_inbound(phone, _audio())
    assert events == ["publish"]


def test_empty_voice_answer_asks_to_type(voice):
    store, sent, events, heard = voice
    phone = "2348012345678"
    store.subs["s1"] = Submission(
        submission_id="s1",
        phone=phone,
        reel_url="u",
        reel_shortcode="sc",
        state=SubmissionState.AWAITING_CLARIFICATION,
        pending_question="Which branch?",
    )
    store.convs[phone] = Conversation(phone=phone, active_submission_id="s1")
    heard["text"] = "   "
    runner.process_inbound(phone, _audio())
    assert not events
    assert store.subs["s1"].state == SubmissionState.AWAITING_CLARIFICATION
    assert "couldn't make out" in sent[-1][1]


def _hours_ago(hours: float) -> str:
    from datetime import UTC, datetime, timedelta

    return (datetime.now(UTC) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _waiting_reel(store, phone: str, state: SubmissionState, **kw) -> Submission:
    sub = Submission(
        submission_id="s1", phone=phone, reel_url="u", reel_shortcode="sc", state=state,
        pending_question="Here's what I got", **kw,
    )  # fmt: skip
    store.subs["s1"] = sub
    store.convs[phone] = Conversation(phone=phone, active_submission_id="s1")
    return sub


def test_long_voice_note_while_confirming_is_a_new_review(voice):
    """A full spoken review must not be published under the reel that was waiting for an OK."""
    store, sent, events, heard = voice
    phone = "2348012345678"
    _waiting_reel(store, phone, SubmissionState.CONFIRMING)
    heard["seconds"] = 95
    heard["text"] = "Okay so I went to Mama Put in Yaba last week and the jollof was amazing..."
    runner.process_inbound(phone, _audio("m8"))
    assert store.subs["s1"].state == SubmissionState.ABANDONED
    assert store.subs["s1"].qa_log == []
    new = store.subs[store.convs[phone].active_submission_id]
    assert new.kind == "voice" and new.wa_media_id == "m8" and new.reel_url is None
    assert events == ["pipeline:None"]
    assert "full review" in sent[0][1] and not any("Listening" in b for _, b in sent)


def test_short_voice_note_while_confirming_is_still_a_reply(voice):
    store, sent, events, heard = voice
    phone = "2348012345678"
    _waiting_reel(store, phone, SubmissionState.AWAITING_CLARIFICATION)
    heard["seconds"] = 29
    runner.process_inbound(phone, _audio())
    assert store.subs["s1"].state != SubmissionState.ABANDONED
    assert events == ["extract:Ikeja, the one on Allen Avenue"]


def test_voice_note_after_reply_window_is_a_new_review(voice, monkeypatch):
    """A reel left waiting since yesterday does not capture today's voice note."""
    store, sent, events, heard = voice
    phone = "2348012345678"
    _waiting_reel(
        store, phone, SubmissionState.AWAITING_CLARIFICATION, state_updated_at=_hours_ago(7)
    )
    monkeypatch.setattr(
        runner, "fetch_voice_note", lambda *a: (_ for _ in ()).throw(AssertionError("fetched"))
    )
    runner.process_inbound(phone, _audio("m9"))
    assert store.subs["s1"].state == SubmissionState.ABANDONED
    new = store.subs[store.convs[phone].active_submission_id]
    assert new.kind == "voice" and new.wa_media_id == "m9"
    assert events == ["pipeline:None"]
    assert "waiting a while" in sent[0][1]


def test_voice_note_within_reply_window_is_a_reply(voice):
    store, sent, events, heard = voice
    phone = "2348012345678"
    _waiting_reel(
        store, phone, SubmissionState.AWAITING_CLARIFICATION, state_updated_at=_hours_ago(5)
    )
    runner.process_inbound(phone, _audio())
    assert events == ["extract:Ikeja, the one on Allen Avenue"]


def test_voice_note_without_submission_starts_voice_review(voice):
    store, sent, events, heard = voice
    phone = "2348012345678"
    runner.process_inbound(phone, _audio("m7"), "Ada")
    conv = store.convs[phone]
    sub = store.subs[conv.active_submission_id]
    assert sub.kind == "voice" and sub.wa_media_id == "m7" and sub.reel_url is None
    assert events == ["pipeline:None"]
    assert "voice note" in sent[0][1]


def test_voice_note_replaces_reel_stuck_waiting_for_video(voice):
    store, sent, events, heard = voice
    phone = "2348012345678"
    store.subs["s1"] = Submission(
        submission_id="s1", phone=phone, reel_url="u", reel_shortcode="sc",
        state=SubmissionState.AWAITING_VIDEO,
    )  # fmt: skip
    store.convs[phone] = Conversation(phone=phone, active_submission_id="s1")
    runner.process_inbound(phone, _audio())
    assert store.subs["s1"].state == SubmissionState.ABANDONED
    assert store.subs[store.convs[phone].active_submission_id].kind == "voice"
    assert events == ["pipeline:None"]


def test_voice_note_while_busy_says_wait(voice):
    store, sent, events, heard = voice
    phone = "2348012345678"
    store.subs["s1"] = Submission(
        submission_id="s1", phone=phone, kind="voice", state=SubmissionState.TRANSCRIBING
    )
    store.convs[phone] = Conversation(phone=phone, active_submission_id="s1")
    runner.process_inbound(phone, _audio())
    assert "Still working" in sent[-1][1] and not events


def test_voice_pipeline_skips_face_check(world, monkeypatch, tmp_path):
    store, sent, events = world
    monkeypatch.undo()  # drop the world stubs for _run_pipeline; re-stub what we need below
    monkeypatch.setattr(runner, "dynamo", store)
    monkeypatch.setattr(runner.wa, "send_text", lambda to, body, **k: sent.append((to, body)))
    monkeypatch.setattr(
        runner, "_extract_and_route", lambda sub, conv, latest_answer: events.append("extract")
    )
    get_settings().work_dir = str(tmp_path)
    uploads: list[str] = []
    monkeypatch.setattr(
        runner.s3, "upload_file", lambda p, key, ct=None: uploads.append(key) or key
    )
    monkeypatch.setattr(runner.s3, "put_json", lambda obj, key: key)
    monkeypatch.setattr(runner.s3, "put_text", lambda text, key: key)

    def fake_fetch(media_id, work):
        (work / "voice.ogg").write_bytes(b"ogg")
        return work / "voice.ogg"

    monkeypatch.setattr(runner, "fetch_voice_note", fake_fetch)
    monkeypatch.setattr(
        runner, "transcode_for_playback", lambda n, out: out.write_bytes(b"m4a") or out
    )
    monkeypatch.setattr(runner, "extract_audio", lambda n, out: out.write_bytes(b"wav") or out)
    monkeypatch.setattr(
        runner,
        "transcribe_audio",
        lambda audio, keywords=None: (
            Transcript(text="I visited Mama Put in Yaba last week and the jollof was excellent"),
            {},
        ),
    )
    monkeypatch.setattr(
        runner, "run_face_check", lambda *a, **k: pytest.fail("SAM must not run for voice")
    )
    sub = Submission(submission_id="v1", phone="2348012345678", kind="voice", wa_media_id="m1")
    store.subs["v1"] = sub
    conv = Conversation(phone=sub.phone, active_submission_id="v1")
    settings = get_settings()
    settings.model_api_key = "k"
    try:
        runner._run_pipeline(sub, conv)
    finally:
        settings.model_api_key = ""
    assert sub.state == SubmissionState.EXTRACTING and sub.face_check is None
    assert sub.s3_voice_key == "submissions/v1/voice.m4a"
    assert "submissions/v1/voice.ogg" in uploads and "submissions/v1/audio.wav" in uploads
    assert events == ["extract"]


def test_publish_voice_review_skips_reel_claim(monkeypatch):
    from app.models import PlaceRef, ReviewExtraction
    from app.pipeline import publish

    saved: dict = {}
    monkeypatch.setattr(publish.dynamo, "claim_reel", lambda *a: pytest.fail("no reel claim"))
    monkeypatch.setattr(publish.dynamo, "put_review", lambda r: saved.setdefault("review", r))
    monkeypatch.setattr(publish.dynamo, "put_submission", lambda s: None)
    monkeypatch.setattr(publish.dynamo, "put_conversation", lambda c: None)
    from app.models import Business, BusinessSummary

    biz = Business(business_id="x", name="n", formatted_address="a", country="NG", review_count=1)
    monkeypatch.setattr(publish.dynamo, "upsert_business_on_publish", lambda ext: biz)
    monkeypatch.setattr(publish.dynamo, "list_reviews", lambda bid: [])
    monkeypatch.setattr(publish.dynamo, "get_summary", lambda bid: None)
    monkeypatch.setattr(publish.dynamo, "put_summary", lambda bid, s: None)
    monkeypatch.setattr(publish, "generate_summary", lambda b, r, p: BusinessSummary())
    monkeypatch.setattr(publish.s3, "put_json", lambda o, k: k)
    monkeypatch.setattr(publish.opensearch, "upsert_business", lambda b, s: None)
    awarded: list[tuple[str, int]] = []
    monkeypatch.setattr(
        publish.dynamo, "add_points", lambda phone, n: awarded.append((phone, n)) or 40
    )
    monkeypatch.setattr(publish.dynamo, "list_reviews_by_reviewer_since", lambda *a, **k: [])
    sent: list[str] = []
    monkeypatch.setattr(publish.wa, "send_text", lambda to, body, **k: sent.append(body))
    ext = ReviewExtraction(
        business=PlaceRef(place_id="x", name="n", formatted_address="a", country="NG"),
        business_name_as_said="n",
    )
    phone = "254712345678"  # Kenyan number: the published review carries its flag country
    sub = Submission(
        submission_id="v1", phone=phone, kind="voice", extraction=ext,
        s3_voice_key="submissions/v1/voice.m4a", state=SubmissionState.CONFIRMING,
    )  # fmt: skip
    review = publish.publish_submission(sub, Conversation(phone=phone))
    assert review is saved["review"]
    assert review.source == "voice" and review.reel_url is None
    assert review.audio_s3_key == "submissions/v1/voice.m4a"
    assert review.reviewer_country == "KE"
    assert sub.state == SubmissionState.PUBLISHED
    assert awarded == [(phone, 10)]
    assert "+10 points" in sent[0] and "you now have 40" in sent[0]


def test_review_audio_endpoint(monkeypatch):
    from app.api import public
    from app.main import app
    from app.models import PlaceRef, ReviewExtraction

    ext = ReviewExtraction(
        business=PlaceRef(place_id="x", name="n", formatted_address="a", country="NG"),
        business_name_as_said="n",
    )
    voice_review = Review(
        review_id="r1", business_id="x", submission_id="v1", reviewer_phone_hash="h",
        source="voice", extraction=ext, audio_s3_key="submissions/v1/voice.m4a",
    )  # fmt: skip
    reel_review = Review(
        review_id="r2", business_id="x", submission_id="s1", reviewer_phone_hash="h",
        reel_url="https://www.instagram.com/reel/abc/", reel_shortcode="abc", extraction=ext,
    )  # fmt: skip
    reviews = {"r1": voice_review, "r2": reel_review}
    monkeypatch.setattr(public.dynamo, "get_review", lambda rid: reviews.get(rid))
    monkeypatch.setattr(
        public.s3, "presigned_url", lambda key, expires=3600: f"https://s3.test/{key}?sig"
    )
    get_settings().public_api_url = "https://api.test"
    assert public.audio_url(voice_review) == "https://api.test/api/review/r1/audio"
    assert public.audio_url(reel_review) is None
    c = TestClient(app)
    r = c.get("/api/review/r1/audio", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "https://s3.test/submissions/v1/voice.m4a?sig"
    assert c.get("/api/review/r2/audio", follow_redirects=False).status_code == 404
    assert c.get("/api/review/nope/audio", follow_redirects=False).status_code == 404


def test_business_endpoint_exposes_reviewer_country_not_hash(monkeypatch):
    from app.api import public
    from app.main import app
    from app.models import Business, PlaceRef, ReviewExtraction

    ext = ReviewExtraction(
        business=PlaceRef(place_id="x", name="n", formatted_address="a", country="NG"),
        business_name_as_said="n",
    )
    flagged = Review(
        review_id="r1", business_id="x", submission_id="s1", reviewer_phone_hash="h",
        reviewer_country="GH", extraction=ext,
    )  # fmt: skip
    legacy = Review(  # published before the field existed: no flag, no crash
        review_id="r0", business_id="x", submission_id="s0", reviewer_phone_hash="h",
        extraction=ext,
    )  # fmt: skip
    biz = Business(business_id="x", name="n", formatted_address="a", country="NG")
    monkeypatch.setattr(public.dynamo, "get_business", lambda bid: biz)
    monkeypatch.setattr(public.dynamo, "get_summary", lambda bid: None)
    monkeypatch.setattr(public.dynamo, "list_reviews", lambda bid: [flagged, legacy])
    body = TestClient(app).get("/api/business/x").json()
    by_id = {r["review_id"]: r for r in body["reviews"]}
    assert by_id["r1"]["reviewer_country"] == "GH"
    assert by_id["r0"]["reviewer_country"] is None
    assert "reviewer_phone_hash" not in by_id["r1"]


# ------------------------------------------------------------------ erasure over WhatsApp
@pytest.fixture
def eraser(world, monkeypatch):
    """`world` plus a scripted erase module: preview counts and a recorded erase call."""
    from app.pipeline import erase

    erased: list[str] = []
    preview = erase.ErasurePreview(reviews=2, submissions=3, points=20)
    monkeypatch.setattr(runner.erase, "preview", lambda phone: preview)

    def fake_erase(phone):
        erased.append(phone)
        return erase.ErasureReport(reference="01REF", reviews=2, submissions=3)

    monkeypatch.setattr(runner.erase, "erase_reviewer", fake_erase)
    return (*world, erased)


def test_delete_request_asks_for_confirmation(eraser):
    store, sent, events, erased = eraser
    for phrase in ("delete my data", "Erase my reviews", "remove my account please", "forget me"):
        runner.process_inbound(PHONE, _text(phrase), "Ada")
        body = sent[-1][1]
        assert "2 published reviews" in body and "1 other submission" in body
        assert "20 points" in body
        assert "Reply *DELETE*" in body
    assert store.convs[PHONE].deletion_requested_at and not erased and not events


def test_delete_confirmation_erases_and_reports_reference(eraser):
    store, sent, events, erased = eraser
    runner.process_inbound(PHONE, _text("delete my data"), "Ada")
    runner.process_inbound(PHONE, _text("DELETE"), "Ada")
    assert erased == [PHONE]
    assert "Done ✅" in sent[-1][1] and "01REF" in sent[-1][1] and "2 reviews" in sent[-1][1]


def _minutes_ago(n: float) -> str:
    from datetime import UTC, datetime, timedelta

    return (datetime.now(UTC) - timedelta(minutes=n)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_delete_confirmation_requires_capitals_and_a_recent_request(eraser):
    store, sent, events, erased = eraser
    # no request at all: DELETE explains the two-step flow instead of erasing
    runner.process_inbound(PHONE, _text("DELETE"), "Ada")
    assert not erased and "first send *delete my data*" in sent[-1][1]
    # a request, then lowercase: a withdrawal, not a confirmation
    runner.process_inbound(PHONE, _text("delete my data"), "Ada")
    runner.process_inbound(PHONE, _text("delete"), "Ada")
    assert not erased and "nothing deleted" in sent[-1][1]
    assert store.convs[PHONE].deletion_requested_at is None
    # a request that is too old
    runner.process_inbound(PHONE, _text("delete my data"), "Ada")
    store.convs[PHONE].deletion_requested_at = _minutes_ago(11)
    runner.process_inbound(PHONE, _text("DELETE"), "Ada")
    assert not erased and "more than 10 minutes old" in sent[-1][1]
    assert store.convs[PHONE].deletion_requested_at is None


def _waiting_submission(store, question="Which Yaba?") -> Submission:
    sub = Submission(
        submission_id="s1",
        phone=PHONE,
        reel_shortcode="sc",
        state=SubmissionState.AWAITING_CLARIFICATION,
        pending_question=question,
    )
    store.subs["s1"] = sub
    store.convs[PHONE] = Conversation(phone=PHONE, active_submission_id="s1")
    return sub


def test_withdrawing_a_deletion_is_not_a_review_answer(eraser):
    store, sent, events, erased = eraser
    sub = _waiting_submission(store)
    runner.process_inbound(PHONE, _text("delete my data"), "Ada")
    runner.process_inbound(PHONE, _text("no"), "Ada")
    assert not erased and sub.qa_log == [] and not events
    assert sub.state == SubmissionState.AWAITING_CLARIFICATION
    assert "nothing deleted" in sent[-1][1] and "Which Yaba?" in sent[-1][1]
    # with the request withdrawn, the next message is an ordinary answer again
    runner.process_inbound(PHONE, _text("Ikeja"), "Ada")
    assert sub.qa_log == [QA(q="Which Yaba?", a="Ikeja")]


def test_expired_delete_is_not_a_correction(eraser):
    store, sent, events, erased = eraser
    sub = _waiting_submission(store)
    sub.state = SubmissionState.CONFIRMING
    runner.process_inbound(PHONE, _text("delete my data"), "Ada")
    store.convs[PHONE].deletion_requested_at = _minutes_ago(11)
    runner.process_inbound(PHONE, _text("DELETE"), "Ada")
    assert not erased and not events and sub.qa_log == []
    assert sub.state == SubmissionState.CONFIRMING


def test_new_reel_withdraws_deletion_and_is_processed(eraser):
    store, sent, events, erased = eraser
    runner.process_inbound(PHONE, _text("delete my data"), "Ada")
    runner.process_inbound(PHONE, _text(REEL), "Ada")
    assert not erased and events == ["pipeline:AbC123"]
    assert "nothing deleted" in sent[-2][1]
    assert store.convs[PHONE].deletion_requested_at is None


def test_messages_during_an_erasure_are_held_off(eraser):
    store, sent, events, erased = eraser
    runner.process_inbound(PHONE, _text("delete my data"), "Ada")
    runner.process_inbound(PHONE, _text("DELETE"), "Ada")
    conv = store.convs[PHONE]
    # the marker goes down before the erasure starts, and the request is no longer pending
    assert conv.erasure_started_at and conv.deletion_requested_at is None
    # the erasure is still running (the fake left the conversation in place): nothing written
    before = (dict(store.convs), dict(store.subs))
    for msg in (_text("hello?"), _text("no"), _text(REEL)):
        runner.process_inbound(PHONE, msg, "Ada")
        assert "in progress" in sent[-1][1]
    assert (dict(store.convs), dict(store.subs)) == before and not events
    assert erased == [PHONE]
    # a marker older than the bound does not lock the number out
    conv.erasure_started_at = _minutes_ago(16)
    runner.process_inbound(PHONE, _text("hello?"), "Ada")
    assert "Afefehub" in sent[-1][1]


def test_withdrawal_never_recreates_a_deleted_conversation(monkeypatch):
    """A withdrawal that read the conversation just before an erasure removed it must not
    write the item back: the store clears the request with a conditional in-place update
    and treats "item gone" as success."""
    from botocore.exceptions import ClientError

    from app.store import dynamo

    calls: list[dict] = []

    class T:
        def update_item(self, **kw):
            calls.append(kw)
            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException", "Message": "gone"}},
                "UpdateItem",
            )

        def put_item(self, **kw):
            raise AssertionError("a withdrawal must never put the conversation item")

    monkeypatch.setattr(dynamo, "_table", lambda: T())
    dynamo.clear_deletion_request(PHONE)  # no exception
    kw = calls[0]
    assert kw["ConditionExpression"] == "attribute_exists(PK)"
    assert kw["UpdateExpression"].startswith("REMOVE deletion_requested_at")
    assert kw["Key"] == {"PK": f"CONV#{PHONE}", "SK": "META"}


def test_video_only_counts_as_content_when_one_is_awaited(eraser, monkeypatch):
    store, sent, events, erased = eraser
    video = {"type": "video", "video": {"id": "v1"}}
    # nothing waiting for a file: the video is just a withdrawal, no false promise
    runner.process_inbound(PHONE, _text("delete my data"), "Ada")
    runner.process_inbound(PHONE, video, "Ada")
    assert "Carrying on" not in sent[-1][1] and "nothing deleted" in sent[-1][1]
    # a submission waiting for the file: withdraw and continue with it
    sub = _waiting_submission(store)
    sub.state = SubmissionState.AWAITING_VIDEO
    monkeypatch.setattr(runner.wa, "download_media", lambda media_id, dest: dest)
    monkeypatch.setattr(runner, "extract_audio", lambda src, dst: dst)
    runner.process_inbound(PHONE, _text("delete my data"), "Ada")
    runner.process_inbound(PHONE, video, "Ada")
    assert any("Carrying on" in b for _, b in sent[-3:])
    assert events[-1] == "pipeline:sc" and not erased


def test_failed_erasure_lifts_the_hold_and_can_be_retried(eraser, monkeypatch):
    store, sent, events, erased = eraser
    attempts: list[str] = []

    def flaky(phone):
        attempts.append(phone)
        if len(attempts) == 1:
            raise RuntimeError("opensearch down")
        from app.pipeline import erase

        return erase.ErasureReport(reference="01REF", reviews=0, submissions=0)

    monkeypatch.setattr(runner.erase, "erase_reviewer", flaky)
    runner.process_inbound(PHONE, _text("delete my data"), "Ada")
    runner.process_inbound(PHONE, _text("DELETE"), "Ada")
    assert attempts == [PHONE] and "went wrong part-way" in sent[-1][1]
    conv = store.convs[PHONE]
    assert conv.erasure_started_at is None and conv.deletion_requested_at is None
    # the chat is not locked: an ordinary message gets an ordinary reply...
    runner.process_inbound(PHONE, _text("hello?"), "Ada")
    assert "Afefehub" in sent[-1][1] and "in progress" not in sent[-1][1]
    # ...and a fresh request + DELETE runs the erasure again
    runner.process_inbound(PHONE, _text("delete my data"), "Ada")
    runner.process_inbound(PHONE, _text("DELETE"), "Ada")
    assert attempts == [PHONE, PHONE] and "Done ✅" in sent[-1][1]


def test_failed_erasure_cannot_publish_the_review_being_erased(eraser, monkeypatch):
    store, sent, events, erased = eraser
    sub = _waiting_submission(store, question="Here's what I got")
    sub.state = SubmissionState.CONFIRMING

    def boom(phone):
        raise RuntimeError("dynamo throttled")

    monkeypatch.setattr(runner.erase, "erase_reviewer", boom)
    runner.process_inbound(PHONE, _text("delete my data"), "Ada")
    runner.process_inbound(PHONE, _text("DELETE"), "Ada")
    assert "went wrong part-way" in sent[-1][1]
    # the submission was abandoned at confirmation, so an "ok" to the error publishes nothing
    assert sub.state == SubmissionState.ABANDONED
    assert store.convs[PHONE].active_submission_id is None
    runner.process_inbound(PHONE, _text("ok"), "Ada")
    assert "publish" not in events and not events


def test_erasure_waits_for_a_running_pipeline(eraser):
    store, sent, events, erased = eraser
    sub = _waiting_submission(store)
    sub.state = SubmissionState.TRANSCRIBING  # a worker is on it right now
    runner.process_inbound(PHONE, _text("delete my data"), "Ada")
    assert "still processing" in sent[-1][1]
    assert store.convs[PHONE].deletion_requested_at is None and not erased
    # a confirmation that lands while a stage is running is refused too
    sub.state = SubmissionState.AWAITING_CLARIFICATION
    runner.process_inbound(PHONE, _text("delete my data"), "Ada")
    sub.state = SubmissionState.EXTRACTING
    runner.process_inbound(PHONE, _text("DELETE"), "Ada")
    assert not erased and "still processing" in sent[-1][1]
    # a stale stage is a crashed one, not a running one: erasure proceeds
    sub.state_updated_at = _minutes_ago(30)
    runner.process_inbound(PHONE, _text("DELETE"), "Ada")
    assert erased == [PHONE]


def test_delete_request_never_counts_as_a_review_answer(eraser):
    store, sent, events, erased = eraser
    store.subs["s1"] = Submission(
        submission_id="s1",
        phone=PHONE,
        reel_shortcode="sc",
        state=SubmissionState.AWAITING_CLARIFICATION,
        pending_question="Which Yaba?",
    )
    store.convs[PHONE] = Conversation(phone=PHONE, active_submission_id="s1")
    runner.process_inbound(PHONE, _text("delete my data"), "Ada")
    runner.process_inbound(PHONE, _text("DELETE"), "Ada")
    assert store.subs["s1"].qa_log == [] and not events and erased == [PHONE]


def test_help_mentions_deletion(world):
    store, sent, events = world
    runner.process_inbound(PHONE, _text("hi"), "Ada")
    assert "delete my data" in sent[0][1]


# ------------------------------------------------------------------ vendor discovery routing
@pytest.fixture
def disco(world, monkeypatch):
    """`world` with the model key set, so discovery runs the (stubbed) agent turn."""
    monkeypatch.setattr(get_settings(), "model_api_key", "k")
    return world


def _waiting(store: FakeStore, state: SubmissionState, question: str = "Which branch?"):
    sub = Submission(
        submission_id="s1",
        phone=PHONE,
        reel_url="u",
        reel_shortcode="sc",
        state=state,
        pending_question=question,
    )
    store.subs["s1"] = sub
    store.convs[PHONE] = Conversation(phone=PHONE, active_submission_id="s1")
    return sub


def test_free_text_is_a_vendor_question(disco):
    store, sent, events = disco
    runner.process_inbound(PHONE, _text("where can I get good jollof in Ikeja"), "Ada")
    assert events == ["discover:where can I get good jollof in Ikeja"]
    assert sent[-1][1] == "vendors for where can I get good jollof in Ikeja"
    assert store.convs[PHONE].discovery.last_query == "where can I get good jollof in Ikeja"


def test_greetings_and_help_still_get_the_intro(disco):
    store, sent, events = disco
    for phrase in ("hi", "Hello!", "help", "menu", "?", "good morning", "how does this work?"):
        runner.process_inbound(PHONE, _text(phrase), "Ada")
        assert "Looking for somewhere good?" in sent[-1][1], phrase
    assert not events


def test_confirm_word_publishes_without_an_intent_check(disco, monkeypatch):
    store, sent, events = disco
    _waiting(store, SubmissionState.CONFIRMING, "Here's what I got")
    monkeypatch.setattr(
        runner.discover, "classify_intent", lambda *a: pytest.fail("intent check ran")
    )
    runner.process_inbound(PHONE, _text("ok"))
    assert events == ["publish"]


def test_number_reply_is_an_answer_without_an_intent_check(disco, monkeypatch):
    store, sent, events = disco
    _waiting(store, SubmissionState.AWAITING_CLARIFICATION, "Which one? 1. A 2. B")
    monkeypatch.setattr(
        runner.discover, "classify_intent", lambda *a: pytest.fail("intent check ran")
    )
    runner.process_inbound(PHONE, _text("2"))
    assert events == ["extract:2"]


def test_vendor_question_mid_review_leaves_the_review_waiting(disco, monkeypatch):
    store, sent, events = disco
    sub = _waiting(store, SubmissionState.AWAITING_CLARIFICATION, "Which branch?")
    asked: list = []
    monkeypatch.setattr(
        runner.discover,
        "classify_intent",
        lambda text, q: asked.append((text, q)) or "discover",
    )
    runner.process_inbound(PHONE, _text("any good barber in Yaba?"))
    assert asked == [("any good barber in Yaba?", "Which branch?")]
    assert events == ["discover:any good barber in Yaba?"]
    assert "still waiting for your reply" in sent[-1][1]
    assert sub.state == SubmissionState.AWAITING_CLARIFICATION
    assert sub.pending_question == "Which branch?" and sub.qa_log == []


def test_answer_mid_review_is_still_an_answer(disco):
    store, sent, events = disco
    sub = _waiting(store, SubmissionState.AWAITING_CLARIFICATION, "Which branch?")
    runner.process_inbound(PHONE, _text("the one on Allen Avenue in Ikeja"))
    assert events == ["extract:the one on Allen Avenue in Ikeja"]
    assert sub.qa_log[-1].a == "the one on Allen Avenue in Ikeja"


def test_vendor_question_while_review_is_processing(disco):
    store, sent, events = disco
    _waiting(store, SubmissionState.TRANSCRIBING, None)
    runner.process_inbound(PHONE, _text("best shawarma in Wuse 2"))
    assert events == ["discover:best shawarma in Wuse 2"]
    assert "still working on your review" in sent[-1][1]


def test_location_pin_reruns_the_last_search_near_it(disco):
    store, sent, events = disco
    runner.process_inbound(PHONE, _text("suya spots"))
    loc = {"type": "location", "location": {"latitude": 6.4474, "longitude": 3.4723}}
    runner.process_inbound(PHONE, loc)
    conv = store.convs[PHONE]
    assert (conv.last_location.lat, conv.last_location.lng) == (6.4474, 3.4723)
    assert events[-1] == "discover:I just shared my location. Same request, near me: suya spots"


def test_location_pin_without_a_search_asks_what_for(disco):
    store, sent, events = disco
    runner.process_inbound(
        PHONE, {"type": "location", "location": {"latitude": 9.07, "longitude": 7.4}}
    )
    assert "What are you looking for nearby?" in sent[-1][1] and not events
    runner.process_inbound(PHONE, {"type": "location", "location": {"latitude": "x"}})
    assert "couldn't read that location" in sent[-1][1]


def test_discovery_daily_cap(disco, monkeypatch):
    store, sent, events = disco
    monkeypatch.setattr(get_settings(), "discovery_daily_limit", 2)
    for _ in range(3):
        runner.process_inbound(PHONE, _text("pharmacy in Lekki"))
    assert len(events) == 2 and "asked me a lot today" in sent[-1][1]


def test_discovery_without_model_key_falls_back_to_plain_search(world, monkeypatch):
    store, sent, events = world
    monkeypatch.setattr(get_settings(), "model_api_key", "")
    hits = [
        {
            "business_id": "ChIJ1",
            "name": "Suya Palace",
            "formatted_address": "Admiralty Way, Lekki",
            "review_count": 2,
            "recommend_rate": 1.0,
            "summary_headline": "Spicy suya, quick service",
        }
    ]
    monkeypatch.setattr(runner.opensearch, "search", lambda q, **kw: hits)
    runner.process_inbound(PHONE, _text("suya in Lekki"))
    body = sent[-1][1]
    assert "1. *Suya Palace*" in body and "100% recommend (2 reviews)" in body
    assert "business?id=ChIJ1" in body and not events


def test_incr_discovery_count_and_erasure_of_counters(monkeypatch):
    from decimal import Decimal

    from app.store import dynamo

    updates: list[dict] = []
    deleted: list[tuple] = []

    class T:
        def update_item(self, **kw):
            updates.append(kw)
            return {"Attributes": {"turns": Decimal(3)}}

        def query(self, **kw):
            assert kw["ExpressionAttributeValues"][":disco"] == "DISCO#"
            return {"Items": [{"SK": "DISCO#2026-11-05"}, {"SK": "DISCO#2026-11-06"}]}

        def delete_item(self, Key):
            deleted.append((Key["PK"], Key["SK"]))

    monkeypatch.setattr(dynamo, "_table", lambda: T())
    assert dynamo.incr_discovery_count("p") == 3
    kw = updates[0]
    assert kw["Key"]["SK"].startswith("DISCO#") and "expires_at" in kw["UpdateExpression"]
    for key in kw["ExpressionAttributeValues"]:
        assert key in kw["UpdateExpression"]
    dynamo.delete_conversation("p")
    assert deleted == [
        ("CONV#p", "META"),
        ("CONV#p", "POINTS"),
        ("CONV#p", "DISCO#2026-11-05"),
        ("CONV#p", "DISCO#2026-11-06"),
    ]
