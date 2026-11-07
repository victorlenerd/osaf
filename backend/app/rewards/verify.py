"""Original-author verification: the reviewer DMs the code we sent on WhatsApp to Afefehub's
Instagram account, from the account that posted the reel. When the sender's username matches
the reel's, the entry becomes an author reel and the Instagram account is linked to the
reviewer, so their later reels count as theirs without another code."""

from __future__ import annotations

import logging
import re

from app.config import get_settings
from app.models import now_iso
from app.rewards import rules
from app.social import instagram
from app.store import dynamo
from app.store import rewards_store as rstore
from app.whatsapp import client as wa

log = logging.getLogger(__name__)

CODE_RE = re.compile(r"\bAFH-?([A-HJ-NP-Z2-9]{6})\b", re.I)


def find_code(text: str) -> str | None:
    m = CODE_RE.search(text or "")
    return f"AFH-{m.group(1).upper()}" if m else None


def _reply(ig, igsid: str, text: str) -> None:
    try:
        ig.send_dm(igsid, text)
    except Exception:  # noqa: BLE001
        log.exception("could not reply on Instagram")


def _credit_reels(reviewer_hash: str, username: str) -> None:
    """Credit every reel this sender published from the now-verified account to them."""
    try:
        for r in dynamo.list_all_reviews_by_reviewer(reviewer_hash):
            if r.source == "reel" and r.ig_username == username and not r.ig_author_verified:
                dynamo.mark_author_verified(r)
    except Exception:  # noqa: BLE001
        log.exception("could not update the credit on %s's reels", reviewer_hash[:8])


def handle_ig_message(igsid: str, text: str, ig=None) -> str:
    """Process one inbound Instagram DM. Returns an outcome label (for logs and tests)."""
    code = find_code(text)
    if not code:
        return "no_code"
    ig = ig or instagram.client_from_settings()
    s = get_settings()
    record = rstore.get_ig_code(code)
    if record is None:
        _reply(
            ig,
            igsid,
            "That code isn't valid or has expired. Send VERIFY to Afefehub on WhatsApp for a "
            "new one.",
        )
        return "unknown_code"
    expected = (record.get("expected_username") or "").lower()
    try:
        username = ig.username_of(igsid)
    except Exception:  # noqa: BLE001
        log.exception("could not look up the Instagram sender")
        return "lookup_failed"  # the code stays valid; the reviewer can send it again
    if not username or username != expected:
        _reply(
            ig,
            igsid,
            f"This code has to be sent from @{expected}, the account that posted the reel.",
        )
        return "wrong_account"

    reviewer_hash = record["phone_hash"]
    entry = rstore.get_entry(reviewer_hash, record["review_id"])
    if entry is None or entry.status != "entered":  # settled entries keep their points
        rstore.delete_ig_code(code)
        _reply(ig, igsid, "That entry is no longer open, so there's nothing to verify.")
        return "entry_closed"
    if not rstore.claim_ig_link(username, reviewer_hash):
        rstore.delete_ig_code(code)
        _reply(
            ig,
            igsid,
            f"@{username} is already linked to another Afefehub number, so it can't be "
            "verified for this one.",
        )
        return "linked_elsewhere"

    entry.kind = "reel_author"
    entry.points = rules.points_for("reel_author")
    entry.ig_verified_at = now_iso()
    entry.ig_code = None
    rstore.put_entry(entry)
    rstore.delete_ig_code(code)
    _credit_reels(reviewer_hash, username)
    _reply(
        ig,
        igsid,
        f"Verified ✅ Your review of {entry.business_name} now earns {entry.points} points.",
    )
    if entry.phone:
        wa.send_text(
            entry.phone,
            f"✅ Instagram verified (@{username}). Your review of *{entry.business_name}* now "
            f"earns {entry.points} pts, and future reels from @{username} count as yours "
            "automatically.",
        )
    log.info("author verified for review %s via @%s", entry.review_id, s.afefehub_ig_handle)
    return "verified"
