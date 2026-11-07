"""What one carousel slide needs from a review, and which reviews may appear at all.

A Candidate carries no reviewer identifier: first name and country only, never the phone hash.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from app.models import Review
from app.pii import redact_phones

DEMO_BUSINESS_PREFIX = "afefe:demo-"
DEMO_REVIEW_PREFIX = "demo-"
MIN_SUMMARY_CHARS = 25
ANONYMOUS = "A reviewer"


# ------------------------------------------------------------------ time window
@dataclass(frozen=True)
class Window:
    since: str  # inclusive, ISO-8601 with Z
    until: str  # exclusive

    def as_dict(self) -> dict:
        return {"since": self.since, "until": self.until}


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def default_window(now: datetime | None = None, days: int = 7) -> Window:
    now = now or datetime.now(UTC)
    return Window(since=_iso(now - timedelta(days=days)), until=_iso(now))


def window_from_dates(since: str | None, until: str | None, *, days: int = 7) -> Window:
    """``YYYY-MM-DD`` bounds: since at 00:00Z inclusive, until at 00:00Z exclusive.

    A missing bound is derived from the other with ``days``; both missing -> last ``days``.
    """
    if not since and not until:
        return default_window(days=days)
    s = datetime.fromisoformat(since).replace(tzinfo=UTC) if since else None
    u = datetime.fromisoformat(until).replace(tzinfo=UTC) if until else None
    if s is None:
        s = u - timedelta(days=days)
    if u is None:
        u = s + timedelta(days=days)
    return Window(since=_iso(s), until=_iso(u))


def in_window(created_at: str, w: Window) -> bool:
    return w.since <= created_at < w.until  # ISO-Z strings sort chronologically


def window_label(w: Window) -> str:
    """Human range for the cover: "20 to 26 Oct 2026", "28 Oct to 3 Nov 2026"."""
    start = datetime.fromisoformat(w.since.replace("Z", "+00:00"))
    end = datetime.fromisoformat(w.until.replace("Z", "+00:00")) - timedelta(seconds=1)
    if start.date() == end.date():
        return f"{start.day} {start:%b %Y}"
    if (start.year, start.month) == (end.year, end.month):
        return f"{start.day} to {end.day} {end:%b %Y}"
    if start.year == end.year:
        return f"{start.day} {start:%b} to {end.day} {end:%b %Y}"
    return f"{start.day} {start:%b %Y} to {end.day} {end:%b %Y}"


# ------------------------------------------------------------------- candidates
class Candidate(BaseModel):
    review_id: str
    business_id: str
    business_name: str
    city: str | None = None
    country: str  # business country, ISO-2
    category: str
    reviewer_first_name: str
    reviewer_country: str | None = None  # ISO-2 from the WhatsApp number, may be unknown
    source: str = "reel"
    recommend: str
    sentiment: str
    summary: str
    good: list[str] = []
    created_at: str
    # where the review's own audio lives, for the reel (no reviewer identifier in any of these)
    submission_id: str = ""
    audio_s3_key: str | None = None  # voice reviews: playable m4a
    video_s3_key: str | None = None  # reel reviews: the archived source video


def first_name(display_name: str | None) -> str:
    """First word of the WhatsApp display name, or a neutral label. Phone-shaped names are
    redacted by app.pii first, so a number never reaches a slide."""
    words = redact_phones((display_name or "").strip()).split()
    word = words[0].strip(",.;:!?\"'()[]") if words else ""
    if not word or "*" in word:
        return ANONYMOUS
    return word[:24]


def to_candidate(review: Review) -> Candidate:
    x = review.extraction
    summary = (x.one_line_summary or "").strip() or (x.good[0].strip() if x.good else "")
    return Candidate(
        review_id=review.review_id,
        business_id=review.business_id,
        business_name=x.business.name,
        city=x.business.city,
        country=x.business.country,
        category=x.category,
        reviewer_first_name=first_name(review.reviewer_display_name),
        reviewer_country=review.reviewer_country,
        source=review.source,
        recommend=x.recommend,
        sentiment=x.overall_sentiment,
        summary=summary,
        good=list(x.good),
        created_at=review.created_at,
        submission_id=review.submission_id,
        audio_s3_key=review.audio_s3_key,
        video_s3_key=review.video_s3_key,
    )


def is_demo(review: Review) -> bool:
    return review.business_id.startswith(DEMO_BUSINESS_PREFIX) or review.review_id.startswith(
        DEMO_REVIEW_PREFIX
    )


def eligible(
    review: Review,
    *,
    min_summary_chars: int = MIN_SUMMARY_CHARS,
    exclude: frozenset[str] | set[str] = frozenset(),
    include_demo: bool = False,
) -> tuple[bool, str]:
    """(ok, reason). Reasons are short tokens the CLI prints next to skipped reviews."""
    if review.status != "published":
        return False, "hidden"
    if review.review_id in exclude:
        return False, "excluded"
    if not include_demo and is_demo(review):
        return False, "demo"
    x = review.extraction
    text = (x.one_line_summary or "").strip() or (x.good[0] if x.good else "")
    if len(text) < min_summary_chars:
        return False, "summary too short"
    return True, ""


def select_candidates(
    reviews: list[Review],
    window: Window,
    *,
    pick: list[str] | None = None,
    exclude: set[str] | None = None,
    include_demo: bool = False,
    max_picks: int | None = 6,
    one_per_business: bool = True,
) -> tuple[list[Candidate], list[tuple[str, str]]]:
    """Reviews in the window that may appear, as candidates, plus (review_id, reason) skips.

    With ``pick`` the result is exactly those ids in that order (ids outside the window or
    ineligible are skipped with a reason). Without it: newest first, one per business unless
    ``one_per_business`` is off, capped at ``max_picks`` (None = all, the pool for ranking).
    """
    exclude = set(exclude or ())
    skipped: list[tuple[str, str]] = []
    ok: dict[str, Candidate] = {}
    for r in sorted(reviews, key=lambda r: r.created_at, reverse=True):
        if not in_window(r.created_at, window):
            skipped.append((r.review_id, "outside window"))
            continue
        good, reason = eligible(r, exclude=exclude, include_demo=include_demo)
        if not good:
            skipped.append((r.review_id, reason))
            continue
        ok[r.review_id] = to_candidate(r)

    if pick:
        out: list[Candidate] = []
        for rid in pick:
            if rid in ok:
                out.append(ok[rid])
            else:
                skipped.append((rid, "not an eligible review in this window"))
        return out, skipped

    out, seen_biz = [], set()
    for c in ok.values():
        if one_per_business and c.business_id in seen_biz:
            skipped.append((c.review_id, "same business already picked"))
            continue
        seen_biz.add(c.business_id)
        out.append(c)
        if max_picks is not None and len(out) >= max_picks:
            break
    return out, skipped
