"""The WhatsApp side of payouts: the ENTER offer after publish, entering reviews, the
author-verification code, bank details, and the *points* reply."""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime

from app.config import get_settings
from app.models import Conversation, EntryKind, Payee, PayoutEntry, PayoutOffer, Review, now_iso
from app.pii import phone_hash
from app.rewards import rules
from app.store import dynamo
from app.store import rewards_store as rstore
from app.whatsapp import client as wa

ENTER_WORDS = re.compile(r"^\s*(enter|enter\s+it|enter\s+all)\s*[.!]*\s*$", re.I)
VERIFY_WORDS = re.compile(r"^\s*(verify|new\s+code|resend\s+code)\s*[.!]*\s*$", re.I)
DETAILS_WORDS = re.compile(
    r"^\s*(bank|payout|payment|account)\s+(details|info)\s*[.!?]*\s*$|^\s*change\s+bank\b", re.I
)
AMAZON_WORDS = re.compile(r"^\s*amazon\b", re.I)
ACCOUNT_RE = re.compile(r"(?<!\d)(\d{10})(?!\d)")
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I
DETAILS_WINDOW_SECONDS = 24 * 3600
KIND_LABELS = {
    "voice": "voice note",
    "reel_unverified": "reel, 0 until you verify it's yours",
    "reel_author": "your own reel ✅",
}
NOT_YOURS_MSG = (
    "Reels only earn payout points when they were posted from your own Instagram account, so "
    "this one can't be entered."
)
# Common Nigerian banks and wallets, to tell the bank apart from the account name.
_BANK_HINTS = re.compile(
    r"\b(bank|gtb|gtco|guaranty|access|zenith|uba|first|opay|palmpay|kuda|moniepoint|fidelity|"
    r"sterling|wema|alat|union|fcmb|stanbic|ecobank|polaris|keystone|providus|jaiz|heritage|"
    r"unity|globus|taj|lotus|vfd|carbon|fairmoney|paga|titan|parallex|premium\s*trust|"
    r"signature|optimus|suntrust|citi|standard\s+chartered)\b",
    re.I,
)
_LABEL = re.compile(
    r"^(bank(\s+name)?|account(\s+(name|number|no\.?))?|acct(\s+name)?|name)\s*[:=\-]?\s*", re.I
)


def new_code() -> str:
    return "AFH-" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))


def _seconds_since(iso: str) -> float:
    return (datetime.now(UTC) - datetime.fromisoformat(iso.replace("Z", "+00:00"))).total_seconds()


# ------------------------------------------------------------------- after publish
def offer_after_publish(review: Review, phone: str, *, banned: bool = False) -> str:
    """Record the ENTER offer for an eligible review and return the line for the "Published!"
    message (empty when there is nothing to say)."""
    s = get_settings()
    reason = rules.ineligible_reason(review, banned=banned)
    if reason == "similar":
        return (
            "This review is very close to one already on Afefehub, so it can't be entered for "
            "a payout."
        )
    if reason:
        return ""
    if review.source == "reel" and not _reel_can_earn(review, phone_hash(phone)):
        return NOT_YOURS_MSG
    rstore.put_offer(
        phone_hash(phone),
        PayoutOffer(review_id=review.review_id, phone=phone),
        s.payout_offer_days * 86400,
    )
    # No month here: the entry joins the window of the day the reviewer replies ENTER (the
    # offer stays open for days), and the ENTER confirmation names that month.
    return (
        "💰 Want this review entered for our monthly payout? Reply *ENTER*.\n"
        f"Voice notes earn {s.points_voice} pts and reels you posted yourself "
        f"{s.points_reel_author} (once you verify they're yours). "
        f"1 pt = up to {rules.naira(s.ngn_per_point)}, paid monthly by bank transfer in Nigeria."
    )


# ------------------------------------------------------------------------- ENTER
def _reel_can_earn(review: Review, reviewer_hash: str) -> bool:
    """A reel earns points only from its author: we must know who posted it, and that
    Instagram account must be unclaimed or already verified to this reviewer."""
    if not review.ig_username:
        return False
    return rstore.get_ig_link(review.ig_username) in (None, reviewer_hash)


def _kind_for(review: Review, reviewer_hash: str) -> EntryKind | None:
    """voice; reel_author when the reel's account is already verified to this reviewer;
    reel_unverified (0 pts until the DM check) when it is unclaimed; None when the reel can
    never earn (posted by someone else's verified account, or the poster is unknown)."""
    if review.source == "voice":
        return "voice"
    if not _reel_can_earn(review, reviewer_hash):
        return None
    if rstore.get_ig_link(review.ig_username or "") == reviewer_hash:
        return "reel_author"
    return "reel_unverified"


def _issue_code(entry: PayoutEntry) -> str:
    s = get_settings()
    if entry.ig_code:
        rstore.delete_ig_code(entry.ig_code)
    code = new_code()
    rstore.put_ig_code(
        code,
        {
            "phone": entry.phone,
            "phone_hash": entry.phone_hash,
            "review_id": entry.review_id,
            "expected_username": entry.ig_username,
        },
        s.ig_code_days * 86400,
    )
    entry.ig_code = code
    rstore.put_entry(entry)
    return code


def verify_instructions(entry: PayoutEntry) -> str:
    s = get_settings()
    return (
        f"📸 *{entry.business_name}* earns {s.points_reel_author} pts once you prove you posted "
        f"the reel, and nothing otherwise: DM "
        f"*{entry.ig_code}* to @{s.afefehub_ig_handle} on Instagram from "
        f"*@{entry.ig_username}* (the account that posted the reel) within "
        f"{s.ig_code_days} days."
    )


def handle_enter(conv: Conversation) -> None:
    phone = conv.phone
    h = phone_hash(phone)
    offers = sorted(rstore.list_offers(h), key=lambda o: o.created_at)
    if not offers:
        wa.send_text(
            phone,
            "There's nothing waiting to be entered right now. After each review is published "
            "I'll ask whether you want it in the monthly payout; reply ENTER then.",
        )
        return
    window = rules.window_for()
    entered: list[PayoutEntry] = []
    to_verify: list[PayoutEntry] = []
    for offer in offers:
        rstore.delete_offer(h, offer.review_id)
        review = dynamo.get_review(offer.review_id)
        if review is None or rules.ineligible_reason(review, banned=False):
            continue
        kind = _kind_for(review, h)
        if kind is None:
            continue
        biz = review.extraction.business
        entry = PayoutEntry(
            review_id=review.review_id,
            phone=phone,
            phone_hash=h,
            business_id=review.business_id,
            business_name=biz.name,
            category=review.extraction.category,
            group=rules.group_for(review.extraction.category),
            kind=kind,
            points=rules.points_for(kind),
            window=window,
            ig_username=review.ig_username,
            ig_verified_at=now_iso() if kind == "reel_author" else None,
            similarity_checked=review.similarity_checked,
        )
        if not rstore.put_entry(entry, only_new=True):
            continue  # already entered (a repeated ENTER)
        entered.append(entry)
        if kind == "reel_unverified":
            _issue_code(entry)
            to_verify.append(entry)

    if not entered:
        wa.send_text(phone, "Those reviews were already entered. Text *points* to see them.")
        return
    lines = "\n".join(
        f"• {e.business_name}: {e.points} pts ({KIND_LABELS[e.kind]})" for e in entered
    )
    body = f"✅ Entered for the *{rules.window_label(window)}* payout:\n{lines}"
    if to_verify:
        body += "\n\n" + "\n\n".join(verify_instructions(e) for e in to_verify)
    body += (
        "\n\nEvery entry is checked by a person before payment, and each category has a "
        "monthly pool, so the final amount can be lower than 1 pt = "
        f"{rules.naira(get_settings().ngn_per_point)} when a category is busy."
    )
    payee = rstore.get_payee(h)
    if payee is None or not payee.complete:
        body += "\n\n" + DETAILS_PROMPT
        conv.payout_details_requested_at = now_iso()
        dynamo.put_conversation(conv)
    wa.send_text(phone, body)


def handle_verify(conv: Conversation) -> None:
    """Re-issue author-verification codes for this window's unverified reels."""
    h = phone_hash(conv.phone)
    pending = [
        e
        for e in rstore.list_entries(h)
        if e.kind == "reel_unverified"
        and e.status == "entered"
        and e.ig_username
        and rstore.get_ig_link(e.ig_username) in (None, h)
    ]
    if not pending:
        wa.send_text(conv.phone, "You have no entered reels waiting for Instagram verification.")
        return
    for e in pending:
        _issue_code(e)
    wa.send_text(conv.phone, "\n\n".join(verify_instructions(e) for e in pending))


# ------------------------------------------------------------------- bank details
DETAILS_PROMPT = (
    "🏦 To get paid, send your *bank name, 10-digit account number and account name*, e.g.\n"
    "GTBank, 0123456789, Ada Obi\n\nPrefer an Amazon gift card? Reply *AMAZON*."
)


def ask_payout_details(conv: Conversation) -> None:
    conv.payout_details_requested_at = now_iso()
    dynamo.put_conversation(conv)
    current = rstore.get_payee(phone_hash(conv.phone))
    body = DETAILS_PROMPT
    if current and current.complete:
        body = f"Your payout details now: {current.masked()}.\n\n" + body
    wa.send_text(conv.phone, body)


def parse_bank_details(text: str) -> tuple[str, str, str] | None:
    """(bank_name, account_number, account_name) from a free-text reply, or None."""
    m = ACCOUNT_RE.search(text or "")
    if not m:
        return None
    rest = text[: m.start()] + "\n" + text[m.end() :]
    parts = []
    for raw in re.split(r"[,\n;|/]+", rest):
        p = _LABEL.sub("", raw.strip(" .:-\t")).strip(" .:-\t")
        if p:
            parts.append(p)
    if len(parts) < 2:
        return None
    bank_idx = next((i for i, p in enumerate(parts) if _BANK_HINTS.search(p)), 0)
    bank = parts.pop(bank_idx)
    name = " ".join(parts)
    if not re.search(r"[A-Za-z]", name):
        return None
    return bank, m.group(1), name


def awaiting_details(conv: Conversation) -> bool:
    at = conv.payout_details_requested_at
    return bool(at) and _seconds_since(at) <= DETAILS_WINDOW_SECONDS


def handle_details_reply(conv: Conversation, text: str) -> bool:
    """True when `text` was the answer to a bank-details question (and has been handled)."""
    if not awaiting_details(conv):
        return False
    h = phone_hash(conv.phone)
    if AMAZON_WORDS.match(text):
        payee = Payee(phone=conv.phone, method="amazon")
    else:
        parsed = parse_bank_details(text)
        if parsed is None:
            if not ACCOUNT_RE.search(text):
                return False  # not an attempt at bank details; route the message normally
            wa.send_text(
                conv.phone,
                "I couldn't read that. Please send the bank name, the 10-digit account number "
                "and the account name, separated by commas.",
            )
            return True
        bank, number, name = parsed
        payee = Payee(
            phone=conv.phone,
            method="bank",
            bank_name=bank,
            account_number=number,
            account_name=name,
        )
    rstore.put_payee(h, payee)
    conv.payout_details_requested_at = None
    dynamo.put_conversation(conv)
    wa.send_text(
        conv.phone,
        f"Saved ✅ We'll pay to: {payee.masked()}.\n\nIf that's wrong, send *bank details* to "
        "change it. The account name should match your bank's records.",
    )
    return True


# -------------------------------------------------------------------------- points
STATUS_LABELS = {
    "entered": "awaiting review",
    "approved": "approved",
    "voided": "not eligible",
    "paid": "paid",
}


def points_text(phone: str) -> str:
    h = phone_hash(phone)
    entries = rstore.list_entries(h)
    window = rules.window_for()
    current = sorted((e for e in entries if e.window == window), key=lambda e: e.entered_at)
    s = get_settings()
    if current:
        lines = "\n".join(
            f"• {e.business_name}: {e.points} pts, {KIND_LABELS[e.kind]} "
            f"({STATUS_LABELS[e.status]})"
            for e in current
        )
        live = sum(e.points for e in current if e.status != "voided")
        body = (
            f"⭐ *{rules.window_label(window)}* payout entries:\n{lines}\n\n"
            f"Total: {live} pts, worth up to {rules.naira(live * s.ngn_per_point)} "
            "(the final amount depends on each category's monthly pool)."
        )
    else:
        body = f"⭐ You have no entries in the {rules.window_label(window)} payout yet."
    paid = sum(e.amount_ngn or 0 for e in entries if e.status == "paid")
    if paid:
        body += f"\n\nPaid to you so far: {rules.naira(paid)}."
    offers = rstore.list_offers(h)
    if offers:
        n = len(offers)
        body += f"\n\n{n} published review{'s' if n != 1 else ''} waiting: reply *ENTER*."
    unverified = [e for e in current if e.kind == "reel_unverified" and e.ig_code]
    if unverified:
        body += "\n\nReels waiting for Instagram verification: reply *VERIFY* for the codes."
    payee = rstore.get_payee(h)
    if payee and payee.complete:
        body += f"\n\nPayout to: {payee.masked()}."
    elif current:
        body += "\n\nNo bank details yet: send *bank details*."
    return body
