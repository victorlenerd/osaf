import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.models import QA, Conversation, Submission, SubmissionState
from app.pipeline import runner


def _payload(text: str, wamid: str = "wamid.1", phone: str = "2348012345678") -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
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
    get_settings().meta_app_secret = ""


class FakeStore:
    def __init__(self):
        self.convs: dict[str, Conversation] = {}
        self.subs: dict[str, Submission] = {}

    def get_conversation(self, phone):
        return self.convs.get(phone)

    def put_conversation(self, c):
        self.convs[c.phone] = c

    def get_submission(self, sid):
        return self.subs.get(sid)

    def put_submission(self, s):
        self.subs[s.submission_id] = s


@pytest.fixture
def world(monkeypatch):
    store = FakeStore()
    sent: list[tuple[str, str]] = []
    events: list[str] = []
    monkeypatch.setattr(runner, "dynamo", store)
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
    return store, sent, events


def _text(body: str) -> dict:
    return {"type": "text", "text": {"body": body}}


def test_junk_gets_help(world):
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
