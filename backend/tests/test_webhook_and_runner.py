import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.models import QA, Conversation, Review, Submission, SubmissionState, Transcript
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
    monkeypatch.setattr(publish.wa, "send_text", lambda *a, **k: None)
    ext = ReviewExtraction(
        business=PlaceRef(place_id="x", name="n", formatted_address="a", country="NG"),
        business_name_as_said="n",
    )
    sub = Submission(
        submission_id="v1", phone="p", kind="voice", extraction=ext,
        s3_voice_key="submissions/v1/voice.m4a", state=SubmissionState.CONFIRMING,
    )  # fmt: skip
    review = publish.publish_submission(sub, Conversation(phone="p"))
    assert review is saved["review"]
    assert review.source == "voice" and review.reel_url is None
    assert review.audio_s3_key == "submissions/v1/voice.m4a"
    assert sub.state == SubmissionState.PUBLISHED


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
