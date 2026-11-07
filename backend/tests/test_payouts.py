"""Payouts: fingerprints and duplicate policy, ENTER offers, Instagram author verification,
bank details, settlement maths, bans and erasure of payout data."""

from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.config import get_settings
from app.fingerprint import check, media, score
from app.fingerprint import text as fptext
from app.models import (
    Business,
    BusinessSummary,
    Conversation,
    FaceCheck,
    Fingerprint,
    Payee,
    PayoutEntry,
    PayoutOffer,
    PlaceRef,
    Review,
    ReviewExtraction,
    SimilarityMatch,
    Submission,
    SubmissionState,
)
from app.pii import phone_hash, redact_phones
from app.rewards import flow, rules, settle, verify

ADA = "2348012345678"
BOB = "2348099999999"
HAS_FFMPEG = shutil.which("ffmpeg") is not None
HAS_FPCALC = shutil.which("fpcalc") is not None


def _review(
    rid: str,
    *,
    phone: str = ADA,
    source: str = "voice",
    country: str = "NG",
    category: str = "restaurant",
    ig_username: str | None = None,
    face: bool = True,
    similarity: SimilarityMatch | None = None,
) -> Review:
    return Review(
        review_id=rid,
        business_id=f"biz-{rid}",
        submission_id=f"sub-{rid}",
        reviewer_phone_hash=phone_hash(phone),
        source=source,
        reel_url="https://www.instagram.com/reel/x/" if source == "reel" else None,
        extraction=ReviewExtraction(
            business=PlaceRef(
                place_id=f"biz-{rid}", name=f"Biz {rid}", formatted_address="a", country=country
            ),
            business_name_as_said="b",
            category=category,
        ),
        face_check=FaceCheck(passed=face) if source == "reel" else None,
        ig_username=ig_username,
        similarity=similarity,
    )


# --------------------------------------------------------------------- fingerprints
def _make_clip(path: Path, source: str, seconds: int = 6) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"{source}=size=320x240:rate=25",
         "-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )  # fmt: skip
    return path


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
def test_reencoded_video_is_a_duplicate_and_other_video_is_not(tmp_path):
    a = _make_clip(tmp_path / "a.mp4", "testsrc")
    b = tmp_path / "b.mp4"  # the same clip re-encoded smaller and at lower quality
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(a), "-vf", "scale=200:150", "-crf", "35",
         str(b)],
        check=True,
    )  # fmt: skip
    c = _make_clip(tmp_path / "c.mp4", "mandelbrot")
    fa, fb, fc = (media.video_fingerprint(p) for p in (a, b, c))
    assert len(fa) == 6 and fa == media.video_fingerprint(a)  # one hash per second, stable
    assert score.video_similarity(fa, fb) >= get_settings().dup_video_threshold
    assert score.video_similarity(fa, fc) < get_settings().similar_video_threshold


@pytest.mark.skipif(not (HAS_FFMPEG and HAS_FPCALC), reason="ffmpeg/fpcalc not installed")
def test_reencoded_audio_is_a_duplicate_and_other_audio_is_not(tmp_path):
    def tone(name, src):
        out = tmp_path / name
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", src, "-t", "20", str(out)],
            check=True,
        )
        return out

    # Two different "melodies" (a tone stepping through a pitch pattern over a low pulse).
    # Structured audio like this, or speech, is what Chromaprint tells apart; two clips of
    # random noise look alike to it (about 0.45), so noise makes a bad "different" sample.
    a = tone(
        "a.wav",
        r"aevalsrc=0.5*sin(2*PI*t*220*pow(2\,floor(mod(t*4\,12))/12))"
        r"+0.2*sin(2*PI*t*55):s=22050",
    )
    b = tmp_path / "b.ogg"  # the same melody re-encoded
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(a), "-b:a", "48k", str(b)], check=True)
    c = tone(
        "c.wav",
        r"aevalsrc=0.5*sin(2*PI*t*330*pow(2\,floor(mod(t*3\,7))*5/12))"
        r"+0.2*sin(2*PI*t*82):s=22050",
    )
    fa, fb, fc = (media.audio_fingerprint(p) for p in (a, b, c))
    assert score.audio_similarity(fa, fb) >= get_settings().dup_audio_threshold
    assert score.audio_similarity(fa, fc) < get_settings().similar_audio_threshold


def test_dhash_is_64_bits_per_frame():
    frame = bytes(range(72))  # strictly increasing: every comparison is "left < right"
    assert media.dhash_frames(frame * 2) == [0, 0]
    assert media.dhash_frames(bytes(reversed(range(72)))) == [(1 << 64) - 1]


def test_audio_similarity_finds_a_trimmed_copy():
    import random

    rng = random.Random(7)
    a = [rng.getrandbits(32) for _ in range(400)]
    trimmed = [v ^ (1 << rng.randrange(32)) for v in a[40:]]  # 5 s cut, a bit flipped each
    other = [rng.getrandbits(32) for _ in range(400)]
    assert score.audio_similarity(a, trimmed) > 0.9
    assert score.audio_similarity(a, other) < 0.2
    assert score.audio_similarity(a[:10], a[:10]) == 0.0  # too short to judge


def test_transcript_similarity():
    t = "I went to Mama Cass in Lekki and the jollof rice was very good but service was slow"
    assert fptext.jaccard(fptext.minhash(t), fptext.minhash(t)) == 1.0
    assert fptext.jaccard(fptext.minhash(t), fptext.minhash(t + " overall a nice spot")) >= 0.6
    other = "Stayed two nights at a hotel in Abuja with a clean pool and friendly reception staff"
    assert fptext.jaccard(fptext.minhash(t), fptext.minhash(other)) < 0.2
    assert len(fptext.band_tokens(fptext.minhash(t))) == fptext.BANDS
    assert fptext.minhash("") == []


def test_judge_orders_duplicate_over_similar():
    exact = SimilarityMatch(review_id="r1", exact=True)
    texty = SimilarityMatch(review_id="r2", text=0.7)
    faint = SimilarityMatch(review_id="r3", text=0.2)
    v = check.judge([faint, texty, exact])
    assert v.duplicate is exact and v.similar is exact and v.best is exact
    v = check.judge([faint, texty])
    assert v.duplicate is None and v.similar is texty
    v = check.judge([faint])
    assert v.similar is None and v.best is faint and v.checked


def test_video_alone_never_blocks_a_review():
    """Same room, same framing, different speech: a lookalike, not a duplicate."""
    room = SimilarityMatch(review_id="r1", video=0.95, audio=0.05, text=0.1)
    assert not check.is_duplicate(room) and not check.is_similar(room)
    assert check.is_lookalike(room)
    reupload = SimilarityMatch(review_id="r2", video=0.95, audio=0.5)
    assert check.is_duplicate(reupload)


def test_blank_frames_do_not_match():
    black = [0] * 30  # a dark or flat video hashes to all zeros
    assert score.video_similarity(black, black) == 0.0
    assert score.video_similarity([0xF0F0F0F0F0F0F0F0] * 5, [0xF0F0F0F0F0F0F0F1] * 5) == 1.0


def test_check_is_unchecked_without_an_index():
    assert check.check(Fingerprint(sha256="x")).checked is False


# --------------------------------------------------------------------- publish
@pytest.fixture
def publishing(monkeypatch):
    from app.pipeline import publish

    saved: dict = {}
    sent: list[str] = []
    biz = Business(business_id="x", name="Biz", formatted_address="a", country="NG", review_count=1)
    stubs = {
        "claim_reel": lambda *a: True,
        "delete_reel_claim": lambda sc: saved.setdefault("released", sc),
        "put_review": lambda r: saved.setdefault("review", r),
        "put_submission": lambda s: None,
        "put_conversation": lambda c: None,
        "upsert_business_on_publish": lambda ext: biz,
        "list_reviews": lambda bid: [],
        "get_summary": lambda bid: None,
        "put_summary": lambda bid, s: None,
        "list_reviews_by_reviewer_since": lambda *a, **k: [],
    }
    for name, fn in stubs.items():
        monkeypatch.setattr(publish.dynamo, name, fn)
    monkeypatch.setattr(publish, "generate_summary", lambda b, r, p: BusinessSummary())
    monkeypatch.setattr(publish.s3, "put_json", lambda o, k: k)
    monkeypatch.setattr(publish.s3, "copy", lambda src, dst: dst)
    monkeypatch.setattr(publish.opensearch, "upsert_business", lambda b, s: None)
    monkeypatch.setattr(publish.wa, "send_text", lambda to, body, **k: sent.append(body))
    return publish, saved, sent


def _sub(**kw) -> Submission:
    ext = ReviewExtraction(
        business=PlaceRef(place_id="x", name="Biz", formatted_address="a", country="NG"),
        business_name_as_said="Biz",
    )
    base = {
        "submission_id": "s1",
        "phone": ADA,
        "kind": "voice",
        "extraction": ext,
        "state": SubmissionState.CONFIRMING,
    }
    return Submission(**(base | kw))


def test_exact_media_copy_is_refused_at_publish(publishing, rewards_db):
    publish, saved, sent = publishing
    rewards_db.media["abc"] = "earlier-review"
    sub = _sub(kind="reel", reel_shortcode="sc", media_sha256="abc")
    assert publish.publish_submission(sub, Conversation(phone=ADA)) is None
    assert sub.state == SubmissionState.REJECTED and "review" not in saved
    assert saved["released"] == "sc"  # the reel lock taken for this attempt is given back
    assert "already on Afefehub" in sent[0]


def test_banned_number_cannot_publish(publishing, rewards_db):
    from app.moderation import bans

    publish, saved, sent = publishing
    bans.ban(phone_hash(ADA), "spam")
    sub = _sub()
    assert publish.publish_submission(sub, Conversation(phone=ADA)) is None
    assert sub.state == SubmissionState.REJECTED and "can no longer submit" in sent[0]


def test_similar_review_publishes_without_an_offer(publishing, rewards_db):
    publish, saved, sent = publishing
    sub = _sub(similarity=SimilarityMatch(review_id="old", text=0.8), similarity_checked=True)
    review = publish.publish_submission(sub, Conversation(phone=ADA))
    assert review is not None and review.similarity.review_id == "old"
    assert not rewards_db.offers and "ENTER" not in sent[0] and "very close" in sent[0]


def test_review_outside_nigeria_gets_no_offer(publishing, rewards_db):
    publish, saved, sent = publishing
    sub = _sub()
    sub.extraction.business.country = "KE"
    publish.publish_submission(sub, Conversation(phone=ADA))
    assert not rewards_db.offers and "ENTER" not in sent[0]


# ------------------------------------------------------------------ ENTER flow
@pytest.fixture
def wa_world(monkeypatch):
    reviews: dict[str, Review] = {}
    convs: dict[str, Conversation] = {}
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(flow.dynamo, "get_review", lambda rid: reviews.get(rid))
    monkeypatch.setattr(flow.dynamo, "put_conversation", lambda c: convs.__setitem__(c.phone, c))
    monkeypatch.setattr(flow.wa, "send_text", lambda to, body, **k: sent.append((to, body)))
    monkeypatch.setattr(verify.wa, "send_text", lambda to, body, **k: sent.append((to, body)))
    monkeypatch.setattr(
        verify.dynamo,
        "list_all_reviews_by_reviewer",
        lambda h: [r for r in reviews.values() if r.reviewer_phone_hash == h],
    )
    monkeypatch.setattr(
        verify.dynamo,
        "mark_author_verified",
        lambda r: setattr(reviews[r.review_id], "ig_author_verified", True),
    )
    return reviews, convs, sent


def _offer(rewards_db, review: Review, phone: str = ADA):
    rewards_db.offers[(phone_hash(phone), review.review_id)] = PayoutOffer(
        review_id=review.review_id, phone=phone
    )


def test_enter_creates_entries_by_kind(wa_world, rewards_db):
    reviews, convs, sent = wa_world
    h = phone_hash(ADA)
    rewards_db.links["ada.eats"] = h  # verified on an earlier reel
    for r in (
        _review("v1"),
        _review("r1", source="reel", ig_username="ada.eats", category="hotel"),
        _review("r2", source="reel", ig_username="new.account", category="shortlet"),
        _review("r3", source="reel"),  # poster unknown: can never earn
    ):
        reviews[r.review_id] = r
        _offer(rewards_db, r)
    conv = Conversation(phone=ADA)
    flow.handle_enter(conv)
    got = {rid: e for (_, rid), e in rewards_db.entries.items()}
    assert (got["v1"].kind, got["v1"].points, got["v1"].group) == ("voice", 5, "restaurants")
    assert (got["r1"].kind, got["r1"].points, got["r1"].group) == ("reel_author", 10, "hotels")
    # an unclaimed account: worth nothing until the reviewer proves they posted it
    assert (got["r2"].kind, got["r2"].points, got["r2"].group) == (
        "reel_unverified",
        0,
        "shortlets",
    )
    assert got["r2"].ig_code in rewards_db.codes and "r3" not in got
    assert rewards_db.codes[got["r2"].ig_code]["expected_username"] == "new.account"
    assert all(e.window == rules.window_for() for e in got.values())
    body = sent[-1][1]
    assert got["r2"].ig_code in body and "@new.account" in body and "bank name" in body
    assert convs[ADA].payout_details_requested_at and not rewards_db.offers
    # a repeated ENTER has nothing left to enter
    flow.handle_enter(conv)
    assert "nothing waiting" in sent[-1][1] and len(rewards_db.entries) == 3


def test_someone_elses_reel_gets_no_offer(rewards_db):
    rewards_db.links["their.account"] = phone_hash(BOB)  # verified to another reviewer
    theirs = _review("r1", source="reel", ig_username="their.account")
    unknown = _review("r2", source="reel")
    for r in (theirs, unknown):
        assert flow.offer_after_publish(r, ADA) == flow.NOT_YOURS_MSG
    assert not rewards_db.offers
    mine = _review("r3", source="reel", ig_username="their.account", phone=BOB)
    assert "ENTER" in flow.offer_after_publish(mine, BOB)


def test_enter_skips_a_review_hidden_since_the_offer(wa_world, rewards_db):
    reviews, convs, sent = wa_world
    r = _review("v1")
    r.status = "hidden"
    reviews["v1"] = r
    _offer(rewards_db, r)
    flow.handle_enter(Conversation(phone=ADA))
    assert not rewards_db.entries and "already entered" in sent[-1][1]


def test_points_text_lists_entries_and_payee(wa_world, rewards_db):
    h = phone_hash(ADA)
    rewards_db.entries[(h, "v1")] = PayoutEntry(
        review_id="v1", phone=ADA, phone_hash=h, business_id="b", business_name="Mama Put",
        kind="voice", points=5, window=rules.window_for(),
    )  # fmt: skip
    rewards_db.payees[h] = Payee(
        phone=ADA, bank_name="GTBank", account_number="0123456789", account_name="Ada Obi"
    )
    body = flow.points_text(ADA)
    assert "Mama Put: 5 pts" in body and "₦5,000" in body and "GTBank ****6789" in body
    assert "0123456789" not in body


# -------------------------------------------------------------------- bank details
@pytest.mark.parametrize(
    "text,expected",
    [
        ("GTBank, 0123456789, Ada Obi", ("GTBank", "0123456789", "Ada Obi")),
        ("Ada Obi\nAccess Bank\n0123456789", ("Access Bank", "0123456789", "Ada Obi")),
        (
            "Bank: Opay; Account number: 8123456789; Account name: Chidi Okeke",
            ("Opay", "8123456789", "Chidi Okeke"),
        ),
        ("0123456789", None),  # no bank or name
        ("GTBank 08012345678 Ada", None),  # an 11-digit phone number is not a NUBAN
    ],
)
def test_parse_bank_details(text, expected):
    assert flow.parse_bank_details(text) == expected


def test_details_reply_saves_payee_only_when_asked(wa_world, rewards_db):
    reviews, convs, sent = wa_world
    conv = Conversation(phone=ADA)
    assert not flow.handle_details_reply(conv, "GTBank, 0123456789, Ada Obi")  # not asked
    flow.ask_payout_details(conv)
    assert not flow.handle_details_reply(conv, "how do I get paid?")  # no number: route on
    assert flow.handle_details_reply(conv, "GTBank, 0123456789, Ada Obi")
    payee = rewards_db.payees[phone_hash(ADA)]
    assert payee.complete and payee.account_name == "Ada Obi"
    assert conv.payout_details_requested_at is None and "****6789" in sent[-1][1]
    flow.ask_payout_details(conv)
    assert flow.handle_details_reply(conv, "AMAZON please")
    assert rewards_db.payees[phone_hash(ADA)].method == "amazon"


def test_account_numbers_are_redacted_in_logs():
    assert "0123456789" not in redact_phones("saved account 0123456789 for Ada")


# ---------------------------------------------------------- Instagram verification
class FakeIG:
    def __init__(self, username: str):
        self.username = username
        self.sent: list[str] = []

    def username_of(self, igsid):
        return self.username

    def send_dm(self, igsid, text):
        self.sent.append(text)


def _entered_reel(rewards_db, phone=ADA, username="ada.eats") -> tuple[PayoutEntry, str]:
    h = phone_hash(phone)
    e = PayoutEntry(
        review_id="r1", phone=phone, phone_hash=h, business_id="b", business_name="Mama Put",
        kind="reel_unverified", points=0, window=rules.window_for(), ig_username=username,
        ig_code="AFH-ABC234",
    )  # fmt: skip
    rewards_db.entries[(h, "r1")] = e
    rewards_db.codes["AFH-ABC234"] = {
        "phone": phone, "phone_hash": h, "review_id": "r1", "expected_username": username,
    }  # fmt: skip
    return e, "AFH-ABC234"


def test_code_from_the_right_account_verifies_the_author(wa_world, rewards_db):
    reviews, convs, sent = wa_world
    _, code = _entered_reel(rewards_db)
    for rid, user in (("r1", "ada.eats"), ("r7", "ada.eats"), ("r8", "other.page")):
        reviews[rid] = _review(rid, source="reel", ig_username=user)
    ig = FakeIG("ada.eats")
    assert verify.handle_ig_message("igsid1", f"hi my code is {code.lower()}", ig) == "verified"
    e = rewards_db.entries[(phone_hash(ADA), "r1")]
    assert (e.kind, e.points, e.ig_code) == ("reel_author", 10, None) and e.ig_verified_at
    assert rewards_db.links["ada.eats"] == phone_hash(ADA) and code not in rewards_db.codes
    assert "Verified" in ig.sent[-1] and "10 pts each" in sent[-1][1]
    # every reel Ada sent from that account is now credited to her, and only those
    credited = {rid for rid, r in reviews.items() if r.ig_author_verified}
    assert credited == {"r1", "r7"}


def test_settled_entry_cannot_be_upgraded(wa_world, rewards_db):
    e, code = _entered_reel(rewards_db)
    rewards_db.entries[(phone_hash(ADA), "r1")].status = "approved"
    assert verify.handle_ig_message("igsid1", code, FakeIG("ada.eats")) == "entry_closed"
    assert rewards_db.entries[(phone_hash(ADA), "r1")].points == 0


def test_verifying_upgrades_every_open_reel_from_that_account(wa_world, rewards_db):
    _, code = _entered_reel(rewards_db)
    h = phone_hash(ADA)
    second = rewards_db.entries[(h, "r1")].model_copy(
        update={"review_id": "r2", "business_name": "Suya Spot", "ig_code": "AFH-XYZ789"}
    )
    other = second.model_copy(update={"review_id": "r3", "ig_username": "other.page"})
    paid = second.model_copy(update={"review_id": "r4", "status": "voided", "ig_code": None})
    for e in (second, other, paid):
        rewards_db.entries[(h, e.review_id)] = e
    rewards_db.codes["AFH-XYZ789"] = {"phone_hash": h}
    assert verify.handle_ig_message("igsid1", code, FakeIG("ada.eats")) == "verified"
    kinds = {rid: e.kind for (_, rid), e in rewards_db.entries.items()}
    assert kinds == {
        "r1": "reel_author", "r2": "reel_author", "r3": "reel_unverified", "r4": "reel_unverified",
    }  # fmt: skip
    assert "AFH-XYZ789" not in rewards_db.codes  # the second code is no longer needed


def test_code_from_another_account_is_refused(wa_world, rewards_db):
    _, code = _entered_reel(rewards_db)
    ig = FakeIG("impostor")
    assert verify.handle_ig_message("igsid1", code, ig) == "wrong_account"
    assert rewards_db.entries[(phone_hash(ADA), "r1")].points == 0
    assert code in rewards_db.codes and "@ada.eats" in ig.sent[-1]


def test_account_linked_to_another_number_cannot_verify(wa_world, rewards_db):
    _, code = _entered_reel(rewards_db)
    rewards_db.links["ada.eats"] = phone_hash(BOB)
    ig = FakeIG("ada.eats")
    assert verify.handle_ig_message("igsid1", code, ig) == "linked_elsewhere"
    assert rewards_db.entries[(phone_hash(ADA), "r1")].points == 0


def test_unknown_code_and_plain_messages(wa_world, rewards_db):
    ig = FakeIG("ada.eats")
    assert verify.handle_ig_message("igsid1", "AFH-ZZZZZZ", ig) == "unknown_code"
    assert verify.handle_ig_message("igsid1", "love your page!", ig) == "no_code"
    assert len(ig.sent) == 1


def test_instagram_webhook_checks_signature_and_dedupes(monkeypatch, rewards_db):
    from app.main import app
    from app.rewards import webhook

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(webhook, "_process", lambda igsid, text: calls.append((igsid, text)))
    monkeypatch.setattr(get_settings(), "meta_app_secret", "secret")
    payload = {
        "object": "instagram",
        "entry": [{"id": "1", "messaging": [
            {"sender": {"id": "igsid1"}, "message": {"mid": "m1", "text": "AFH-ABC234"}},
            {"sender": {"id": "me"}, "message": {"mid": "m2", "text": "x", "is_echo": True}},
        ]}],
    }  # fmt: skip
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    client = TestClient(app)
    bad = client.post("/webhooks/instagram", content=body, headers={"X-Hub-Signature-256": "x"})
    assert bad.status_code == 403
    for _ in range(2):  # Meta redelivers: the second copy is ignored
        r = client.post("/webhooks/instagram", content=body, headers={"X-Hub-Signature-256": sig})
        assert r.status_code == 200
    assert calls == [("igsid1", "AFH-ABC234")]


# ------------------------------------------------------------------------- settle
def _entry(rid, group, points, phone=ADA, status="entered") -> PayoutEntry:
    return PayoutEntry(
        review_id=rid, phone=phone, phone_hash=phone_hash(phone), business_id="b",
        kind="voice", points=points, group=group, window="2026-11", status=status,
        entered_at=f"2026-11-01T00:00:{int(rid[1:]):02d}Z",
    )  # fmt: skip


def test_under_pool_pays_full_rate_and_over_pool_pays_pro_rata(monkeypatch):
    monkeypatch.setattr(get_settings(), "pool_hotels_ngn", 1_000_000)
    monkeypatch.setattr(get_settings(), "pool_others_ngn", 30_000)
    entries = [_entry("e1", "hotels", 10), _entry("e2", "others", 10, phone=BOB)]
    entries += [_entry(f"e{i}", "others", 5) for i in range(3, 7)]  # others: 30 pts vs ₦30k
    entries.append(_entry("e7", "others", 5))  # 35 pts vs ₦30k -> ₦857.14/pt
    settle.apply_decisions(entries, {e.review_id: ("", "") for e in entries})  # all approved
    groups, payees = settle.compute(entries)
    assert groups["hotels"].rate_ngn == 1000 and entries[0].amount_ngn == 10_000
    assert groups["others"].rate_ngn == pytest.approx(30_000 / 35)
    assert groups["others"].paid_ngn <= 30_000
    assert sum(e.amount_ngn for e in entries if e.group == "others") == groups["others"].paid_ngn
    by = {p.phone_hash: p for p in payees}
    assert by[phone_hash(BOB)].amount_ngn == 8571
    assert by[phone_hash(ADA)].amount_ngn == 10_000 + 5 * 4285


def test_decisions_void_and_ban(monkeypatch):
    entries = [
        _entry("e1", "others", 5),
        _entry("e2", "others", 5),
        _entry("e3", "others", 5, phone=BOB),
        _entry("e4", "others", 5, phone=BOB, status="paid"),
    ]
    seen = {"e1": ("VOID", "blurry"), "e2": ("", ""), "e3": ("ban", "spam same reel")}
    changed, to_ban, missing = settle.apply_decisions(entries, seen)
    status = {e.review_id: e.status for e in entries}
    assert status == {"e1": "voided", "e2": "approved", "e3": "voided", "e4": "paid"}
    assert to_ban == {phone_hash(BOB)} and len(changed) == 3 and not missing
    with pytest.raises(ValueError):
        settle.normalise_decision("aprove")
    reel = _entry("e5", "others", 0)
    reel.kind = "reel_unverified"
    settle.apply_decisions([reel], {"e5": ("approve", "")})
    assert reel.status == "voided" and reel.note == "author not verified"


def test_entries_nobody_saw_are_never_approved_by_default():
    """A reel verified (or an entry made) after the export is not in the sheet: it stays open
    for the next export rather than being paid unseen. A ban still reaches it."""
    late = _entry("e1", "others", 10)
    late.kind = "reel_author"  # verified between export and settle
    seen = _entry("e2", "others", 5)
    changed, _, missing = settle.apply_decisions([late, seen], {"e2": ("", "")})
    assert late.status == "entered" and missing == [late] and changed == [seen]
    groups, payees = settle.compute([late, seen])
    assert [p.amount_ngn for p in payees] == [5000]
    banned = _entry("e3", "others", 5, phone=BOB)
    shown = _entry("e4", "others", 5, phone=BOB)
    settle.apply_decisions([banned, shown], {"e4": ("ban", "spam")})
    assert banned.status == "voided" and shown.status == "voided"


# ---------------------------------------------------------------------------- bans
def test_ban_voids_open_entries_and_hides_reviews(monkeypatch, rewards_db):
    from app.moderation import bans

    h = phone_hash(ADA)
    open_e = _entry("e1", "others", 5)
    paid_e = _entry("e2", "others", 5, status="paid")
    rewards_db.entries[(h, "e1")] = open_e
    rewards_db.entries[(h, "e2")] = paid_e
    rewards_db.offers[(h, "v9")] = PayoutOffer(review_id="v9", phone=ADA)
    rewards_db.links["ada.eats"] = h
    reviews = [_review("v1"), _review("v2")]
    hidden: list[str] = []
    rebuilt: list[list[str]] = []
    monkeypatch.setattr(bans.dynamo, "list_all_reviews_by_reviewer", lambda hh: reviews)
    monkeypatch.setattr(bans.dynamo, "set_review_status", lambda r, s: hidden.append(r.review_id))
    monkeypatch.setattr(
        bans.erase,
        "rebuild_businesses",
        lambda ids: rebuilt.append(ids) or bans.erase.ErasureReport(reference="x"),
    )
    b = bans.ban(h, "spam", note="same reel 5x", hide_reviews=True)
    assert rewards_db.entries[(h, "e1")].status == "voided"
    assert rewards_db.entries[(h, "e2")].status == "paid"
    assert not rewards_db.offers and b.entries_voided == 1 and b.reviews_hidden == 2
    assert hidden == ["v1", "v2"] and rebuilt == [["biz-v1", "biz-v2"]]
    assert b.ig_usernames == ["ada.eats"] and bans.ig_account_banned("Ada.Eats")
    assert bans.is_banned(ADA)
    bans.unban(h)
    assert not bans.is_banned(ADA) and not bans.ig_account_banned("ada.eats")


# ------------------------------------------------------------------------ erasure
def test_erasure_keeps_paid_entries_without_the_number(rewards_db):
    from app.moderation import bans
    from app.pipeline import erase

    h = phone_hash(ADA)
    bans.ban(h, "spam")
    rewards_db.entries[(h, "e1")] = _entry("e1", "others", 5)
    rewards_db.entries[(h, "e2")] = _entry("e2", "others", 5, status="paid")
    rewards_db.entries[(h, "e1")].ig_code = "AFH-ABC234"
    rewards_db.codes["AFH-ABC234"] = {"phone_hash": h}
    rewards_db.payees[h] = Payee(phone=ADA, method="amazon")
    rewards_db.offers[(h, "v9")] = PayoutOffer(review_id="v9", phone=ADA)
    rewards_db.links["ada.eats"] = h
    report = erase.ErasureReport(reference="r")
    erase._erase_payouts(ADA, report)
    left = rewards_db.entries
    assert list(left) == [(h, "e2")] and left[(h, "e2")].phone is None
    assert not rewards_db.payees and not rewards_db.offers and not rewards_db.codes
    assert not rewards_db.links and h in rewards_db.bans  # the ban outlives erasure
    assert report.paid_entries_kept == 1 and report.payout_items == 3


# ------------------------------------------------------------------- WhatsApp template
@respx.mock
def test_send_template_returns_message_id(monkeypatch):
    from app.whatsapp import client as wa

    monkeypatch.setattr(get_settings(), "whatsapp_access_token", "t")
    monkeypatch.setattr(get_settings(), "whatsapp_phone_number_id", "123")
    route = respx.post("https://graph.facebook.com/v21.0/123/messages").mock(
        return_value=httpx.Response(200, json={"messages": [{"id": "wamid.1"}]})
    )
    assert wa.send_template(ADA, "payout_sent", ["Ada", "₦5,000", "November 2026"]) == "wamid.1"
    sent = json.loads(route.calls[0].request.content)
    assert sent["type"] == "template" and sent["template"]["name"] == "payout_sent"
    params = sent["template"]["components"][0]["parameters"]
    assert [p["text"] for p in params] == ["Ada", "₦5,000", "November 2026"]


# ------------------------------------------------------------------------- credit
def test_reels_are_credited_to_their_poster_until_the_sender_proves_authorship():
    from app.credit import credit

    voice = _review("v1")
    voice.reviewer_display_name, voice.reviewer_country = "Ada Obi", "NG"
    c = credit(voice)
    assert (c.name, c.country, c.handle, c.shared_by) == ("Ada Obi", "NG", None, None)

    shared = _review("r1", source="reel", ig_username="lagos.foodie")
    shared.reviewer_display_name, shared.reviewer_country = "Ada Obi", "NG"
    c = credit(shared)
    assert (c.name, c.country, c.handle, c.shared_by) == (None, None, "lagos.foodie", "Ada")

    shared.ig_author_verified = True
    c = credit(shared)
    assert (c.name, c.country, c.handle, c.shared_by) == ("Ada Obi", "NG", "lagos.foodie", None)

    legacy = _review("r2", source="reel")  # published before the poster was recorded
    legacy.reviewer_display_name = "Ada Obi"
    assert credit(legacy).name == "Ada Obi" and credit(legacy).handle is None


def test_business_page_and_carousel_use_the_credit(monkeypatch):
    from app.api import public
    from app.main import app
    from app.social.candidates import to_candidate

    shared = _review("r1", source="reel", ig_username="lagos.foodie")
    shared.reviewer_display_name, shared.reviewer_country = "Ada Obi", "NG"
    biz = Business(business_id="x", name="n", formatted_address="a", country="NG")
    monkeypatch.setattr(public.dynamo, "get_business", lambda bid: biz)
    monkeypatch.setattr(public.dynamo, "get_summary", lambda bid: None)
    monkeypatch.setattr(public.dynamo, "list_reviews", lambda bid: [shared])
    body = TestClient(app).get("/api/business/x").json()
    r = body["reviews"][0]
    assert (r["reviewer_display_name"], r["reviewer_country"]) == (None, None)
    assert (r["reel_author"], r["shared_by"]) == ("lagos.foodie", "Ada")
    cand = to_candidate(shared)
    assert cand.reviewer_first_name == "@lagos.foodie" and cand.reviewer_country is None


def test_publish_credits_a_reel_from_an_account_already_verified_to_the_sender(
    publishing, rewards_db
):
    publish, saved, sent = publishing
    rewards_db.links["ada.eats"] = phone_hash(ADA)
    sub = _sub(kind="reel", reel_shortcode="sc", ig_username="ada.eats")
    assert publish.publish_submission(sub, Conversation(phone=ADA)).ig_author_verified
    sub = _sub(kind="reel", reel_shortcode="sc2", ig_username="stranger", submission_id="s2")
    assert not publish.publish_submission(sub, Conversation(phone=ADA)).ig_author_verified


# ------------------------------------------------------- reel sent as a WhatsApp file
def test_reel_sent_on_whatsapp_still_learns_its_poster(monkeypatch, tmp_path):
    from app.pipeline import runner
    from app.pipeline.download import DownloadError, ReelMeta

    calls: list[str] = []

    def meta(url, work):
        calls.append(url)
        return ReelMeta(username="ada.eats", uploader_id="42", posted_at="2026-11-01T10:00:00Z")

    monkeypatch.setattr(runner, "reel_metadata", meta)
    sub = Submission(submission_id="s1", phone=ADA, reel_url="https://www.instagram.com/reel/x/")
    runner._fill_reel_owner(sub, tmp_path)
    assert (sub.ig_username, sub.ig_uploader_id) == ("ada.eats", "42")
    runner._fill_reel_owner(sub, tmp_path)  # already known: no second lookup
    assert len(calls) == 1

    def refuse(url, work):
        raise DownloadError("rate limited")

    monkeypatch.setattr(runner, "reel_metadata", refuse)
    other = Submission(submission_id="s2", phone=ADA, reel_url="https://www.instagram.com/reel/y/")
    runner._fill_reel_owner(other, tmp_path)  # Instagram refused: publishes without a poster
    assert other.ig_username is None


def test_near_copy_published_since_the_pipeline_check_is_refused(publishing, monkeypatch):
    """Two near-identical reels in flight together both pass the pipeline check; whichever
    is confirmed second is caught by the check repeated at publish."""
    publish, saved, sent = publishing
    monkeypatch.setattr(publish, "_load_fingerprint", lambda sub: Fingerprint(audio=[1]))
    monkeypatch.setattr(
        publish.fpcheck,
        "check",
        lambda fp, **k: check.Verdict(
            checked=True, duplicate=SimilarityMatch(review_id="twin", audio=0.95)
        ),
    )
    sub = _sub(kind="reel", reel_shortcode="sc", similarity_checked=True)
    assert publish.publish_submission(sub, Conversation(phone=ADA)) is None
    assert sub.state == SubmissionState.REJECTED and sub.error == "duplicate of review twin"
    assert "review" not in saved and "already on Afefehub" in sent[0]
