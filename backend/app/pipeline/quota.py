"""Per-reviewer weekly quota: at most N published reviews in any rolling 7-day window.

The published reviews under GSI1 REVIEWER#<hash> are the source of truth, so rejected or
abandoned attempts never count and deleting a business frees its slots.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.pii import phone_hash
from app.store import dynamo

__all__ = ["WeeklyQuota", "humanize_until", "phone_hash", "slots_line", "weekly_quota"]

WINDOW = timedelta(days=7)
ISO = "%Y-%m-%dT%H:%M:%SZ"


def _parse(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


@dataclass
class WeeklyQuota:
    used: int
    limit: int
    next_open_at: str | None = None  # ISO Z; set only when the limit is reached

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    @property
    def exhausted(self) -> bool:
        return self.used >= self.limit


def weekly_quota(phone: str, now: datetime | None = None) -> WeeklyQuota:
    now = now or datetime.now(UTC)
    limit = get_settings().weekly_review_limit
    since = (now - WINDOW).strftime(ISO)
    reviews = dynamo.list_reviews_by_reviewer_since(phone_hash(phone), since)
    q = WeeklyQuota(used=len(reviews), limit=limit)
    if q.exhausted and reviews:
        q.next_open_at = (_parse(reviews[0].created_at) + WINDOW).strftime(ISO)
    return q


def humanize_until(iso: str, now: datetime | None = None) -> str:
    """'in about 5 hours', 'tomorrow', 'in 3 days'. Never earlier than 'in about 1 hour'."""
    now = now or datetime.now(UTC)
    seconds = (_parse(iso) - now).total_seconds()
    if seconds < 86400:
        hours = max(1, math.ceil(seconds / 3600))
        return f"in about {hours} hour{'s' if hours != 1 else ''}"
    days = math.ceil(seconds / 86400)
    return "tomorrow" if days == 1 else f"in {days} days"


def slots_line(q: WeeklyQuota) -> str:
    if q.exhausted:
        when = humanize_until(q.next_open_at) if q.next_open_at else "soon"
        return f"You've used all {q.limit} review slots for this week; the next one opens {when}."
    n = q.remaining
    return f"You have {n} review slot{'s' if n != 1 else ''} left this week."
