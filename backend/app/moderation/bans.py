"""Bans for spam and abuse. A ban is keyed by the phone hash, so it survives erasure and can
be applied from a review id (which only carries the hash). Banning:
  - stops the number at intake (runner) and at publish;
  - voids every entry that has not been paid yet, and withdraws open ENTER offers;
  - marks the reviewer's verified Instagram accounts, whose reels are then refused;
  - optionally hides all of the reviewer's reviews and rebuilds the businesses they were on.
"""

from __future__ import annotations

import logging

from app.models import Ban, now_iso
from app.pii import phone_hash
from app.pipeline import erase
from app.store import dynamo
from app.store import rewards_store as rstore

log = logging.getLogger(__name__)

REASONS = ("spam", "duplicate", "fake", "abuse", "other")


def is_banned(phone: str) -> bool:
    return rstore.get_ban(phone_hash(phone)) is not None


def ig_account_banned(username: str | None) -> bool:
    return bool(username) and rstore.ig_account_banned(username or "")


def ban(
    reviewer_hash: str,
    reason: str,
    *,
    note: str = "",
    hide_reviews: bool = False,
    by: str = "operator",
) -> Ban:
    if reason not in REASONS:
        raise ValueError(f"reason must be one of {', '.join(REASONS)}")
    b = rstore.get_ban(reviewer_hash) or Ban(phone_hash=reviewer_hash, reason=reason)
    b.reason, b.note, b.banned_by = reason, note, by
    b.hide_reviews = b.hide_reviews or hide_reviews

    for e in rstore.list_entries(reviewer_hash):
        if e.status in ("entered", "approved"):
            e.status = "voided"
            e.note = f"banned: {reason}"
            e.decided_at = now_iso()
            rstore.put_entry(e)
            b.entries_voided += 1
            if e.ig_code:
                rstore.delete_ig_code(e.ig_code)
    for o in rstore.list_offers(reviewer_hash):
        rstore.delete_offer(reviewer_hash, o.review_id)

    b.ig_usernames = sorted(set(b.ig_usernames) | set(rstore.list_ig_links(reviewer_hash)))

    if hide_reviews:
        touched: list[str] = []
        for r in dynamo.list_all_reviews_by_reviewer(reviewer_hash):
            if r.status == "published":
                dynamo.set_review_status(r, "hidden")
                b.reviews_hidden += 1
                touched.append(r.business_id)
        if touched:
            report = erase.rebuild_businesses(list(dict.fromkeys(touched)))
            if report.errors:
                log.error("ban %s: rebuild errors %s", reviewer_hash[:8], report.errors)

    rstore.put_ban(b)
    return b


def unban(reviewer_hash: str, *, unhide_reviews: bool = False) -> Ban | None:
    """Lift a ban. Voided entries stay voided; hidden reviews come back only on request."""
    b = rstore.get_ban(reviewer_hash)
    if b is None:
        return None
    rstore.delete_ban(b)
    if unhide_reviews:
        touched: list[str] = []
        for r in dynamo.list_all_reviews_by_reviewer(reviewer_hash):
            if r.status == "hidden":
                dynamo.set_review_status(r, "published")
                touched.append(r.business_id)
        if touched:
            erase.rebuild_businesses(list(dict.fromkeys(touched)))
    return b


BANNED_MSG = (
    "This number can no longer submit reviews to Afefehub because of repeated breaches of our "
    "Terms (spam, duplicate or misleading reviews). You can still text *delete my data* to "
    "erase everything we hold. If you think this is a mistake, email legal@afefehub.com."
)
