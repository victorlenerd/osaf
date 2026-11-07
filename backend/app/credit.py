"""Who a published review is credited to.

A voice note is credited to the person who sent it. A reel is the work of the Instagram
account that posted it, which may not be the person who sent us the link: unless the sender
has proven they posted it (the author check, app/rewards/verify.py), the reel is credited to
its Instagram handle, and the sender is shown only as the person who shared it, without their
country flag (the flag comes from the sender's number, not the creator's).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models import Review
from app.pii import redact_phones


@dataclass
class Credit:
    name: str | None  # the reviewer's WhatsApp display name, when the review is theirs
    country: str | None  # ISO-2 of the credited reviewer's number; None for a shared reel
    handle: str | None  # Instagram username of the account that posted the reel
    shared_by: str | None  # first name of the sender, when the reel is credited to its poster


def first_word(display_name: str | None) -> str | None:
    """First word of a WhatsApp display name; None when empty or phone-shaped."""
    words = redact_phones((display_name or "").strip()).split()
    word = words[0].strip(",.;:!?\"'()[]") if words else ""
    if not word or "*" in word:
        return None
    return word[:24]


def credit(r: Review) -> Credit:
    if r.source == "reel" and r.ig_username:
        if r.ig_author_verified:
            return Credit(r.reviewer_display_name, r.reviewer_country, r.ig_username, None)
        return Credit(None, None, r.ig_username, first_word(r.reviewer_display_name))
    # voice notes, and reels published before we recorded who posted them
    return Credit(r.reviewer_display_name, r.reviewer_country, None, None)
