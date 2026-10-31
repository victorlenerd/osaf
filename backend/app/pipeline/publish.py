"""Publish a confirmed submission: review + business upsert + summary + search index."""

from __future__ import annotations

import hashlib
import logging

from ulid import ULID

from app.agent.summary import generate_summary
from app.config import get_settings
from app.models import Conversation, Review, Submission, SubmissionState, now_iso
from app.store import dynamo, opensearch, s3
from app.whatsapp import client as wa

log = logging.getLogger(__name__)


def phone_hash(phone: str) -> str:
    return hashlib.sha256((get_settings().phone_hash_salt + phone).encode()).hexdigest()[:24]


def business_url(business_id: str) -> str:
    return f"{get_settings().public_site_url}/business?id={business_id}"


def publish_submission(sub: Submission, conv: Conversation) -> Review | None:
    ext = sub.extraction
    assert ext is not None, "cannot publish without an extraction"
    review_id = str(ULID())
    if sub.kind == "reel" and not dynamo.claim_reel(sub.reel_shortcode or "", review_id):
        sub.state = SubmissionState.REJECTED
        sub.error = "reel already reviewed"
        sub.state_updated_at = now_iso()
        dynamo.put_submission(sub)
        wa.send_text(
            sub.phone, "That reel has already been published on Afefehub, so I won't add it twice."
        )
        return None

    review = Review(
        review_id=review_id,
        business_id=ext.business.place_id,
        submission_id=sub.submission_id,
        reviewer_phone_hash=phone_hash(sub.phone),
        reviewer_display_name=conv.display_name,
        source=sub.kind,
        reel_url=sub.reel_url,
        reel_shortcode=sub.reel_shortcode,
        extraction=ext,
        transcript_s3_key=sub.s3_transcript_key,
        video_s3_key=sub.s3_video_key,
        audio_s3_key=sub.s3_voice_key,
        face_check=sub.face_check,
    )
    dynamo.put_review(review)
    business = dynamo.upsert_business_on_publish(ext)

    reviews = dynamo.list_reviews(business.business_id)
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

    sub.review_id = review_id
    sub.business_id = business.business_id
    sub.pending_question = None
    sub.state = SubmissionState.PUBLISHED
    sub.state_updated_at = now_iso()
    dynamo.put_submission(sub)

    conv.active_submission_id = None
    if ext.business.city:
        conv.profile_city = ext.business.city
    if ext.business.country:
        conv.profile_country = ext.business.country
    dynamo.put_conversation(conv)

    wa.send_text(
        sub.phone,
        f"Published! 🎉 Your review of {business.name} is live:\n"
        f"{business_url(business.business_id)}\n\n"
        f"That's review #{business.review_count} for this business. Send another reel or "
        "voice note anytime.",
    )
    return review
