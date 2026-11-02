"""Erase everything Afefehub holds about one WhatsApp number (the privacy policy's right to
erasure, and Meta's user-data-deletion requirement).

What goes, in order:
  1. every review the number published: the review item, its by-id pointer, the media,
     transcript and agent trace under submissions/<id>/, and the one-review-per-reel lock;
  2. every other submission (rejected, abandoned, in flight) and its S3 folder;
  3. each affected business is rebuilt from the reviews that remain: counters recomputed,
     summary regenerated, search document reindexed; a business left with no review is
     removed entirely, together with its summary history;
  4. the conversation record and the points balance.

Only a dated, keyed-hash receipt (no number) is kept, so a later question "was my data
deleted?" can be answered. The privacy policy allows keeping the hash for 12 months.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from ulid import ULID

from app.agent.summary import generate_summary
from app.models import now_iso
from app.pii import phone_hash, phone_label
from app.store import dynamo, opensearch, s3

log = logging.getLogger(__name__)

RECEIPT_TTL_SECONDS = 365 * 86400


@dataclass
class ErasureReport:
    reference: str
    reviews: int = 0
    submissions: int = 0
    objects: int = 0  # S3 objects removed
    businesses_rebuilt: list[str] = field(default_factory=list)
    businesses_removed: list[str] = field(default_factory=list)
    points_forfeited: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.errors


@dataclass
class ErasurePreview:
    reviews: int
    submissions: int
    points: int


def preview(phone: str) -> ErasurePreview:
    """What an erasure would remove, for the confirmation message and the dry run."""
    return ErasurePreview(
        reviews=len(dynamo.list_all_reviews_by_reviewer(phone_hash(phone))),
        submissions=len(dynamo.list_all_submissions_for_phone(phone)),
        points=dynamo.get_points(phone),
    )


def _delete_folder(report: ErasureReport, submission_id: str, done: set[str]) -> None:
    if submission_id in done:  # a published review and its submission share one folder
        return
    done.add(submission_id)
    try:
        report.objects += s3.delete_prefix(f"submissions/{submission_id}/")
    except Exception as e:  # noqa: BLE001
        report.errors.append(f"s3 submissions/{submission_id}/: {e!r}")


def erase_reviewer(phone: str) -> ErasureReport:
    report = ErasureReport(reference=str(ULID()))
    label = phone_label(phone)
    report.points_forfeited = dynamo.get_points(phone)

    # 1. published reviews
    touched: dict[str, None] = {}
    folders: set[str] = set()
    for review in dynamo.list_all_reviews_by_reviewer(phone_hash(phone)):
        dynamo.delete_review(review)
        touched[review.business_id] = None
        _delete_folder(report, review.submission_id, folders)
        if review.reel_shortcode:
            dynamo.delete_reel_claim(review.reel_shortcode)
        report.reviews += 1

    # 2. the rest of the submissions (rejected, abandoned, waiting, or published long ago)
    for sub in dynamo.list_all_submissions_for_phone(phone):
        _delete_folder(report, sub.submission_id, folders)
        if sub.reel_shortcode:
            dynamo.delete_reel_claim(sub.reel_shortcode)
        dynamo.delete_submission(sub.submission_id)
        report.submissions += 1

    # 3. businesses: rebuild from what remains, or remove when nothing does
    for business_id in touched:
        try:
            _rebuild_business(report, business_id)
        except Exception as e:  # noqa: BLE001
            log.exception("could not rebuild %s after erasing %s", business_id, label)
            report.errors.append(f"business {business_id}: {e!r}")

    # 4. the number itself
    dynamo.delete_conversation(phone)

    _write_receipt(phone, report)
    log.info(
        "erased %s: %d reviews, %d submissions, %d objects, %d businesses rebuilt, %d removed",
        label,
        report.reviews,
        report.submissions,
        report.objects,
        len(report.businesses_rebuilt),
        len(report.businesses_removed),
    )
    return report


def _rebuild_business(report: ErasureReport, business_id: str) -> None:
    business = dynamo.rebuild_business_counters(business_id)
    if business is None:
        dynamo.delete_business(business_id)
        opensearch.delete_business(business_id)
        try:
            safe = business_id.replace("/", "_")
            report.objects += s3.delete_prefix(f"businesses/{safe}/summary_history/")
        except Exception as e:  # noqa: BLE001
            report.errors.append(f"s3 businesses/{business_id}/: {e!r}")
        report.businesses_removed.append(business_id)
        return
    reviews = dynamo.list_reviews(business_id)
    # No `previous`: the old summary may paraphrase the review that was just removed.
    summary = generate_summary(business, reviews, None)
    dynamo.put_summary(business_id, summary)
    opensearch.upsert_business(business, summary)
    report.businesses_rebuilt.append(business_id)


def _write_receipt(phone: str, report: ErasureReport) -> None:
    """A dated proof of erasure keyed by the reference the reviewer was given. Holds the keyed
    hash of the number, never the number."""
    try:
        dynamo.put_erasure_receipt(
            report.reference,
            {
                "reviewer_hash": phone_hash(phone),
                "erased_at": now_iso(),
                "reviews": report.reviews,
                "submissions": report.submissions,
                "objects": report.objects,
                "businesses_rebuilt": report.businesses_rebuilt,
                "businesses_removed": report.businesses_removed,
                "errors": report.errors,
                "expires_at": int(time.time()) + RECEIPT_TTL_SECONDS,
            },
        )
    except Exception as e:  # noqa: BLE001
        log.exception("could not write erasure receipt %s", report.reference)
        report.errors.append(f"receipt: {e!r}")
