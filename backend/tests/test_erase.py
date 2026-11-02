"""Right to erasure: every store the reviewer touched is cleaned, businesses are rebuilt
from the reviews that remain, and a business with none left disappears."""

from __future__ import annotations

from app.models import BusinessSummary, PlaceRef, Review, ReviewExtraction, Submission
from app.pii import phone_hash
from app.pipeline import erase

ADA = "2348012345678"
BOB = "254700000000"


def _review(rid: str, phone: str, business: str, *, shortcode: str | None = None) -> Review:
    return Review(
        review_id=rid,
        business_id=business,
        submission_id=f"sub-{rid}",
        reviewer_phone_hash=phone_hash(phone),
        reel_shortcode=shortcode,
        extraction=ReviewExtraction(
            business=PlaceRef(place_id=business, name="n", formatted_address="a", country="NG"),
            business_name_as_said="n",
            recommend="yes",
            keywords=["jollof"],
        ),
    )


class FakeDynamo:
    def __init__(self):
        self.reviews: list[Review] = []
        self.subs: list[Submission] = []
        self.points: dict[str, int] = {}
        self.convs: set[str] = set()
        self.reel_claims: set[str] = set()
        self.businesses: set[str] = set()
        self.summaries: dict[str, BusinessSummary] = {}
        self.receipts: dict[str, dict] = {}
        self.deleted_businesses: list[str] = []

    # reads
    def list_all_reviews_by_reviewer(self, h):
        return [r for r in self.reviews if r.reviewer_phone_hash == h]

    def list_all_submissions_for_phone(self, phone):
        return [s for s in self.subs if s.phone == phone]

    def list_reviews(self, business_id, limit=100):
        return [r for r in self.reviews if r.business_id == business_id]

    def get_points(self, phone):
        return self.points.get(phone, 0)

    # deletes
    def delete_review(self, r):
        self.reviews.remove(r)

    def delete_reel_claim(self, sc):
        self.reel_claims.discard(sc)

    def delete_submission(self, sid):
        self.subs = [s for s in self.subs if s.submission_id != sid]

    def delete_conversation(self, phone):
        self.convs.discard(phone)
        self.points.pop(phone, None)

    def delete_business(self, bid):
        self.businesses.discard(bid)
        self.summaries.pop(bid, None)
        self.deleted_businesses.append(bid)
        return 1

    # rebuild
    def rebuild_business_counters(self, bid):
        from app.models import Business

        left = self.list_reviews(bid)
        if not left:
            return None
        return Business(
            business_id=bid, name="n", formatted_address="a", country="NG", review_count=len(left)
        )

    def put_summary(self, bid, s):
        self.summaries[bid] = s

    def put_erasure_receipt(self, ref, record):
        self.receipts[ref] = record


class FakeS3:
    def __init__(self):
        self.prefixes: list[str] = []
        self.fail_on: set[str] = set()

    def delete_prefix(self, prefix):
        if prefix in self.fail_on:
            raise RuntimeError("AccessDenied")
        self.prefixes.append(prefix)
        return 3


class FakeSearch:
    def __init__(self):
        self.upserted: list[str] = []
        self.deleted: list[str] = []

    def upsert_business(self, b, s):
        self.upserted.append(b.business_id)

    def delete_business(self, bid):
        self.deleted.append(bid)


def _world(monkeypatch):
    db, s3, search = FakeDynamo(), FakeS3(), FakeSearch()
    monkeypatch.setattr(erase, "dynamo", db)
    monkeypatch.setattr(erase, "s3", s3)
    monkeypatch.setattr(erase, "opensearch", search)
    monkeypatch.setattr(
        erase,
        "generate_summary",
        lambda b, reviews, previous: BusinessSummary(review_count=len(reviews)),
    )
    # Ada: a reel review on "shared" (Bob also reviewed it), a voice review on "solo",
    # one rejected submission. Bob keeps his review.
    db.reviews += [
        _review("a1", ADA, "shared", shortcode="reelA"),
        _review("a2", ADA, "solo"),
        _review("b1", BOB, "shared", shortcode="reelB"),
    ]
    db.subs += [
        Submission(submission_id="sub-a1", phone=ADA, reel_shortcode="reelA"),
        Submission(submission_id="sub-a2", phone=ADA, kind="voice"),
        Submission(submission_id="sub-a3", phone=ADA, reel_shortcode="reelX"),
        Submission(submission_id="sub-b1", phone=BOB, reel_shortcode="reelB"),
    ]
    db.reel_claims |= {"reelA", "reelB", "reelX"}
    db.businesses |= {"shared", "solo"}
    db.summaries["shared"] = BusinessSummary(headline="old")
    db.points[ADA] = 20
    db.points[BOB] = 10
    db.convs |= {ADA, BOB}
    return db, s3, search


def test_preview_counts(monkeypatch):
    _world(monkeypatch)
    p = erase.preview(ADA)
    assert (p.reviews, p.submissions, p.points) == (2, 3, 20)


def test_erasure_removes_everything_of_one_reviewer_only(monkeypatch):
    db, s3, search = _world(monkeypatch)
    report = erase.erase_reviewer(ADA)

    assert report.clean and report.reviews == 2 and report.submissions == 3
    assert report.points_forfeited == 20
    # reviews, submissions, conversation, points, reel locks: Ada's gone, Bob's intact
    assert [r.review_id for r in db.reviews] == ["b1"]
    assert [s.submission_id for s in db.subs] == ["sub-b1"]
    assert db.convs == {BOB} and db.points == {BOB: 10}
    assert db.reel_claims == {"reelB"}
    # each submission folder removed exactly once (published ones are listed twice)
    assert sorted(s3.prefixes) == [
        "businesses/solo/summary_history/",
        "submissions/sub-a1/",
        "submissions/sub-a2/",
        "submissions/sub-a3/",
    ]
    assert report.objects == 3 * 4
    # the shared business is rebuilt from Bob's review without the old summary; solo is gone
    assert report.businesses_rebuilt == ["shared"] and report.businesses_removed == ["solo"]
    assert db.summaries["shared"].review_count == 1 and db.summaries["shared"].headline == ""
    assert search.upserted == ["shared"] and search.deleted == ["solo"]
    assert db.deleted_businesses == ["solo"] and "businesses/solo/summary_history/" in s3.prefixes
    # the receipt holds the hash and counts, never the number
    receipt = db.receipts[report.reference]
    assert receipt["reviewer_hash"] == phone_hash(ADA) and receipt["reviews"] == 2
    assert ADA not in str(receipt)


def test_s3_failure_is_reported_but_does_not_stop_the_erasure(monkeypatch):
    db, s3, search = _world(monkeypatch)
    s3.fail_on.add("submissions/sub-a2/")
    report = erase.erase_reviewer(ADA)
    assert not report.clean and any("sub-a2" in e for e in report.errors)
    assert [r.review_id for r in db.reviews] == ["b1"] and db.convs == {BOB}
    assert db.receipts[report.reference]["errors"] == report.errors


def test_rebuild_counters_expression_and_empty_business(monkeypatch):
    """DynamoDB rejects UpdateItem with unused ExpressionAttributeValues; and a business with
    no review left must come back as None, not be written with zero counters."""
    from app.store import dynamo

    calls: list[dict] = []
    items = [_review("a1", ADA, "x"), _review("b1", BOB, "x")]
    items[1].extraction.recommend = "no"
    items[1].extraction.keywords = ["Jollof", "suya"]

    class T:
        def query(self, **kw):
            return {"Items": [dynamo._to_item(r) for r in items]}

        def update_item(self, **kw):
            calls.append(kw)

        def get_item(self, **kw):
            return {
                "Item": {"business_id": "x", "name": "n", "formatted_address": "a", "country": "NG"}
            }

    monkeypatch.setattr(dynamo, "_table", lambda: T())
    assert dynamo.rebuild_business_counters("x") is not None
    kw = calls[0]
    for key in kw["ExpressionAttributeValues"]:
        assert key in kw["UpdateExpression"]
    vals = kw["ExpressionAttributeValues"]
    assert vals[":n"] == 2 and vals[":rc"] == {"yes": 1, "no": 1, "maybe": 0}
    assert vals[":kw"] == {"jollof": 2, "suya": 1} and vals[":names"] == ["n"]
    assert "updated_at" not in kw["UpdateExpression"]

    items.clear()
    assert dynamo.rebuild_business_counters("x") is None and len(calls) == 1
