"""Monthly settlement maths, kept free of I/O so it can be tested on its own.

Each category group has a naira pool. Approved points are worth ngn_per_point each, unless
the group's approved points are worth more than its pool; then every point in that group is
worth pool / points (pro rata). Amounts are rounded down to the naira per entry, so a group
never pays out more than its pool.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.config import get_settings
from app.models import PayoutEntry, now_iso
from app.rewards import rules

DECISIONS = ("approve", "void", "ban")


@dataclass
class GroupTotal:
    group: str
    pool_ngn: int
    points: int = 0
    rate_ngn: float = 0.0
    paid_ngn: int = 0


@dataclass
class PayeeTotal:
    phone_hash: str
    phone: str | None
    amount_ngn: int = 0
    review_ids: list[str] = field(default_factory=list)


def normalise_decision(raw: str | None) -> str:
    """A blank decision means approve; anything else must be one of DECISIONS."""
    d = (raw or "").strip().lower()
    if not d:
        return "approve"
    if d not in DECISIONS:
        raise ValueError(f"unknown decision {raw!r}; use approve, void or ban")
    return d


def apply_decisions(
    entries: list[PayoutEntry], decisions: dict[str, tuple[str, str]]
) -> tuple[list[PayoutEntry], set[str], list[PayoutEntry]]:
    """Set each open entry to approved or voided from {review_id: (decision, note)}, where
    `decisions` holds every row of the reviewed spreadsheet (a blank decision is approve).

    Returns (changed entries, phone hashes to ban, entries missing from the sheet). An entry
    nobody saw (entered, or changed, after the export) is never approved by default: it is
    left open for the next export. A ban voids every open entry of that reviewer in the
    window, seen or not. A reel whose author was never verified is voided whatever the
    decision: it is worth nothing. Paid and already-voided entries are left alone."""
    to_ban: set[str] = set()
    for e in entries:
        decision, _ = decisions.get(e.review_id, ("", ""))
        if e.review_id in decisions and normalise_decision(decision) == "ban":
            to_ban.add(e.phone_hash)
    changed: list[PayoutEntry] = []
    missing: list[PayoutEntry] = []
    for e in entries:
        if e.status not in ("entered", "approved"):
            continue
        if e.phone_hash in to_ban:
            d, note = "void", decisions.get(e.review_id, ("", ""))[1] or "reviewer banned"
        elif e.review_id not in decisions:
            missing.append(e)
            continue
        else:
            decision, note = decisions[e.review_id]
            d = normalise_decision(decision)
            if e.kind == "reel_unverified":
                d, note = "void", "author not verified"
        e.status = "approved" if d == "approve" else "voided"
        e.note = note or None
        e.decided_at = now_iso()
        changed.append(e)
    return changed, to_ban, missing


def compute(entries: list[PayoutEntry]) -> tuple[dict[str, GroupTotal], list[PayeeTotal]]:
    """Rates per group and amounts per entry and payee, over the approved entries.

    Mutates each approved entry's rate_ngn and amount_ngn."""
    per_point = get_settings().ngn_per_point
    groups = {g: GroupTotal(group=g, pool_ngn=pool) for g, pool in rules.pools_ngn().items()}
    approved = [e for e in entries if e.status == "approved"]
    for e in approved:
        groups.setdefault(e.group, GroupTotal(group=e.group, pool_ngn=0)).points += e.points
    for g in groups.values():
        if g.points:
            g.rate_ngn = min(float(per_point), g.pool_ngn / g.points)
    payees: dict[str, PayeeTotal] = {}
    for e in sorted(approved, key=lambda x: x.entered_at):
        g = groups[e.group]
        e.rate_ngn = round(g.rate_ngn, 4)
        e.amount_ngn = math.floor(e.points * g.rate_ngn)
        g.paid_ngn += e.amount_ngn
        p = payees.setdefault(e.phone_hash, PayeeTotal(phone_hash=e.phone_hash, phone=e.phone))
        p.amount_ngn += e.amount_ngn
        p.review_ids.append(e.review_id)
    return groups, sorted(payees.values(), key=lambda p: -p.amount_ngn)
