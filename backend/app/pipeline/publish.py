"""Publish a confirmed submission: review + business upsert + summary + search index, then
the payout offer (reviews no longer earn points by being published; the reviewer ENTERs
them, see app/rewards/flow.py)."""

from __future__ import annotations

import logging

from ulid import ULID

from app.agent.places import country_from_phone
from app.agent.summary import generate_summary
from app.config import get_settings
from app.fingerprint import check as fpcheck
from app.fingerprint import index as fpindex
from app.models import Conversation, Fingerprint, Review, Submission, SubmissionState, now_iso
from app.moderation import bans
from app.pipeline.quota import phone_hash, slots_line, weekly_quota
from app.rewards import flow as rewards
from app.seo import site as seo_site
from app.seo.slugs import business_path
from app.store import dynamo, opensearch, s3
from app.store import rewards_store as rstore
from app.whatsapp import client as wa

__all__ = ["business_url", "phone_hash", "publish_submission"]

log = logging.getLogger(__name__)

PENDING_DUPLICATE_MSG = (
    "A {what} matching this one is being published on Afefehub right now, so I won't add "
    "it twice. If it hasn't appeared in a few minutes, send yours again."
)
DUPLICATE_MSG = (
    "This {what} matches a review that's already on Afefehub, so I won't publish it again. "
    "Send a fresh review of a place you visited anytime."
)


def business_url(business_id: str, slug: str | None = None) -> str:
    """The canonical, crawlable page when the slug is known; the interactive page otherwise."""
    site = get_settings().public_site_url.rstrip("/")
    if slug:
        return f"{site}{business_path(slug)}"
    return f"{site}/business?id={business_id}"


def _reject(sub: Submission, reason: str, message: str) -> None:
    sub.state = SubmissionState.REJECTED
    sub.error = reason
    sub.state_updated_at = now_iso()
    dynamo.put_submission(sub)
    wa.send_text(sub.phone, message)


def _retain_media(sub: Submission, review_id: str) -> dict[str, str]:
    """Copy what a published review needs out of submissions/ (which expires after 30 days)
    into reviews/<id>/. Returns {old_key: new_key}; a failed copy keeps the old key."""
    keys = [
        sub.s3_video_key,
        sub.s3_voice_key,
        sub.s3_transcript_key,
        s3.Keys.transcript_txt(sub.submission_id) if sub.s3_transcript_key else None,
        sub.s3_facecheck_key,
        sub.s3_fingerprint_key,
    ]
    moved: dict[str, str] = {}
    for key in filter(None, keys):
        try:
            moved[key] = s3.copy(key, s3.Keys.review_copy(review_id, key))
        except Exception:  # noqa: BLE001
            log.exception("could not retain %s for review %s", key, review_id)
    return moved


def _load_fingerprint(sub: Submission) -> Fingerprint | None:
    if not sub.s3_fingerprint_key:
        return None
    try:
        return Fingerprint(**s3.get_json(sub.s3_fingerprint_key))
    except Exception:  # noqa: BLE001
        log.exception("could not load fingerprint for %s", sub.submission_id)
        return None


def publish_submission(sub: Submission, conv: Conversation) -> Review | None:
    ext = sub.extraction
    assert ext is not None, "cannot publish without an extraction"
    what = "voice note" if sub.kind == "voice" else "reel"
    if bans.is_banned(sub.phone):
        _reject(sub, "banned", bans.BANNED_MSG)
        return None
    review_id = str(ULID())
    reviewer = phone_hash(sub.phone)
    # Locks taken for this review, undone if publishing fails before the review is stored:
    # a lock left behind would make a retry look like a duplicate of itself.
    undo: list = []

    def release() -> None:
        for step in reversed(undo):
            try:
                step()
            except Exception:  # noqa: BLE001
                log.exception("could not release a publish lock for %s", review_id)

    if sub.kind == "reel":
        if not dynamo.claim_reel(sub.reel_shortcode or "", review_id):
            _reject(
                sub,
                "reel already reviewed",
                "That reel has already been published on Afefehub, so I won't add it twice.",
            )
            return None
        undo.append(lambda: dynamo.delete_reel_claim(sub.reel_shortcode or ""))
    if sub.media_sha256:
        if not rstore.claim_media(sub.media_sha256, review_id):
            release()
            _reject(sub, "duplicate media", DUPLICATE_MSG.format(what=what))
            return None
        undo.append(lambda: rstore.delete_media_claim(sub.media_sha256 or ""))

    try:
        fp = _load_fingerprint(sub)
        if fp is not None:
            # Index this fingerprint first, then compare it with every earlier review. The
            # pipeline's check ran before the reviewer confirmed (possibly hours ago), and two
            # near-copies confirmed at the same moment would each miss the other if we only
            # indexed after publishing; this way the later of the two always sees the earlier.
            try:
                fpindex.put(
                    review_id, ext.business.place_id, reviewer, now_iso(), fp, status="pending"
                )
            except Exception:  # noqa: BLE001
                log.exception("fingerprint index failed for %s", review_id)
            undo.append(lambda: fpindex.delete(review_id))
            verdict = fpcheck.check(fp, exclude=review_id, before=review_id)
            if verdict.duplicate is not None:
                release()
                message = PENDING_DUPLICATE_MSG if verdict.duplicate.pending else DUPLICATE_MSG
                _reject(
                    sub,
                    f"duplicate of review {verdict.duplicate.review_id}",
                    message.format(what=what),
                )
                return None
            if verdict.checked:
                sub.similarity_checked = True
                sub.similarity = verdict.similar

        moved = _retain_media(sub, review_id)

        def kept(key: str | None) -> str | None:
            return moved.get(key, key) if key else None

        review = Review(
            review_id=review_id,
            business_id=ext.business.place_id,
            submission_id=sub.submission_id,
            reviewer_phone_hash=reviewer,
            reviewer_display_name=conv.display_name,
            reviewer_country=country_from_phone(sub.phone),
            source=sub.kind,
            reel_url=sub.reel_url,
            reel_shortcode=sub.reel_shortcode,
            extraction=ext,
            transcript_s3_key=kept(sub.s3_transcript_key),
            video_s3_key=kept(sub.s3_video_key),
            audio_s3_key=kept(sub.s3_voice_key),
            face_check=sub.face_check,
            ig_username=sub.ig_username,
            ig_author_verified=bool(sub.ig_username)
            and rstore.get_ig_link(sub.ig_username) == reviewer,
            ig_uploader_id=sub.ig_uploader_id,
            ig_posted_at=sub.ig_posted_at,
            media_sha256=sub.media_sha256,
            fingerprint_s3_key=kept(sub.s3_fingerprint_key),
            similarity=sub.similarity,
            similarity_checked=sub.similarity_checked,
        )
        dynamo.put_review(review)
    except Exception:
        release()
        raise
    if fp is not None:
        try:
            fpindex.mark_published(review_id)
        except Exception:  # noqa: BLE001
            # Not fatal: check.py confirms an old pending entry against the stored review.
            log.exception("could not mark fingerprint %s published", review_id)
    business = dynamo.upsert_business_on_publish(ext)

    reviews = [r for r in dynamo.list_reviews(business.business_id) if r.status == "published"]
    previous = dynamo.get_summary(business.business_id)
    summary = generate_summary(business, reviews, previous)
    dynamo.put_summary(business.business_id, summary)
    s3.put_json(
        summary.model_dump(), s3.Keys.summary_history(business.business_id, summary.last_updated)
    )
    try:
        opensearch.upsert_business(business, summary)
    except Exception:  # noqa: BLE001
        log.exception("opensearch upsert failed for %s", business.business_id)
    try:
        seo_site.publish_business_page(business.business_id)
    except Exception:  # noqa: BLE001
        log.exception("page render failed for %s", business.business_id)

    sub.review_id = review_id
    sub.business_id = business.business_id
    sub.pending_question = None
    sub.state = SubmissionState.PUBLISHED
    sub.state_updated_at = now_iso()
    dynamo.put_submission(sub)

    q = weekly_quota(sub.phone)  # the review just written already counts against this week

    conv.active_submission_id = None
    if ext.business.city:
        conv.profile_city = ext.business.city
    if ext.business.country:
        conv.profile_country = ext.business.country
    dynamo.put_conversation(conv)

    body = (
        f"Published! 🎉 Your review of {business.name} is live:\n"
        f"{business_url(business.business_id, business.slug)}\n\n"
        f"That's review #{business.review_count} for this business."
    )
    s = get_settings()
    if s.payouts_enabled:
        # The offer is recorded only once the PUBLISHED marker is durable.
        offer = rewards.offer_after_publish(review, sub.phone)
        if offer:
            body += f"\n\n{offer}"
        body += (
            f"\n\n{slots_line(q)} Send another reel or voice note anytime; text *points* to "
            "see your payout entries."
        )
    else:
        # Before the payout launch: the current scheme, a flat reward on every review.
        total = dynamo.add_points(sub.phone, s.points_per_review)
        body += (
            f" ⭐ +{s.points_per_review} points, you now have {total}.\n\n{slots_line(q)} "
            "Send another reel or voice note anytime; text *points* to check your balance."
        )
    wa.send_text(sub.phone, body)
    return review
