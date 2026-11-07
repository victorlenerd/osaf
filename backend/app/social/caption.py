"""Instagram captions: the weekly carousel's, and each single-review Reel's. Deterministic
templates; the only model input is the carousel's optional one-line hook."""

from __future__ import annotations

import re

from app.social.candidates import Candidate, Window, window_label
from app.social.flags import flag_emoji

MAX_CAPTION_CHARS = 2200
MAX_HASHTAGS = 30
DEFAULT_HOOK = "Real people, real places. This week's reviews on Afefehub:"
DEFAULT_HASHTAGS = [
    "afefehub",
    "reviewsoftheweek",
    "africanbusiness",
    "smallbusiness",
    "realreviews",
]
_HASHTAG_RE = re.compile(r"(?<!\w)#\w+")


def count_hashtags(text: str) -> int:
    return len(_HASHTAG_RE.findall(text))


def _quote(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0]
    return cut.rstrip(",;:") + "…"


def _city_tags(picks: list[Candidate], limit: int = 3) -> list[str]:
    out: list[str] = []
    for c in picks:
        tag = re.sub(r"[^a-z]", "", (c.city or "").lower())
        if tag and tag not in out:
            out.append(tag)
        if len(out) >= limit:
            break
    return out


def how_to_submit(wa_number: str = "") -> str:
    if wa_number:
        return (
            "Been somewhere worth talking about? Post a public reel and WhatsApp the link to "
            f"{wa_number}, or just send us a voice note. We transcribe it and add it to the "
            "business page."
        )
    return (
        "Been somewhere worth talking about? Post a public reel and WhatsApp us the link, "
        "or just send us a voice note. We transcribe it and add it to the business page."
    )


def _tags(picks: list[Candidate], hashtags: list[str] | None) -> str:
    tags = list(hashtags if hashtags is not None else DEFAULT_HASHTAGS)
    for t in _city_tags(picks):
        if t not in tags:
            tags.append(t)
    return " ".join(f"#{t}" for t in tags[:MAX_HASHTAGS])


def build_caption(
    picks: list[Candidate],
    window: Window,
    *,
    hook: str | None = None,
    wa_number: str = "",
    site_url: str = "afefehub.com",
    hashtags: list[str] | None = None,
    max_quote: int = 120,
) -> str:
    tags = _tags(picks, hashtags)
    how = how_to_submit(wa_number)

    for limit in (max_quote, 80, 50):
        lines = []
        for c in picks:
            flag = flag_emoji(c.reviewer_country)
            where = f"{c.business_name}, {c.city}" if c.city else c.business_name
            lines.append(f"{flag + ' ' if flag else ''}{where}: “{_quote(c.summary, limit)}”")
        text = "\n\n".join(
            [
                (hook or DEFAULT_HOOK).strip(),
                "\n".join(lines),
                how,
                site_url,
                tags,
            ]
        )
        if len(text) <= MAX_CAPTION_CHARS:
            return text
    raise ValueError(f"caption is {len(text)} chars even with short quotes; fewer picks needed")


def build_review_caption(
    cand: Candidate,
    window: Window,
    *,
    wa_number: str = "",
    site_url: str = "afefehub.com",
    hashtags: list[str] | None = None,
) -> str:
    """One review's Reel: who and where, their summary, what was good, then the same how-to,
    site and hashtags as the carousel. First name and flag only, like the slides."""
    flag = flag_emoji(cand.reviewer_country)
    where = f"{cand.business_name}, {cand.city}" if cand.city else cand.business_name
    head = f"{flag + ' ' if flag else ''}{cand.reviewer_first_name} on {where}"
    for limit in (400, 200, 100):
        good = "\n".join(f"+ {_quote(g, 120)}" for g in cand.good[:3])
        parts = [head, f"“{_quote(cand.summary, limit)}”"]
        if good:
            parts.append(good)
        parts += [
            f"From this week's Reviews of the week ({window_label(window)}). "
            "Sound on to hear it in their own words.",
            how_to_submit(wa_number),
            site_url,
            _tags([cand], hashtags),
        ]
        text = "\n\n".join(parts)
        if len(text) <= MAX_CAPTION_CHARS:
            return text
    raise ValueError(f"review caption is {len(text)} chars even with a short quote")


def assert_caption_ok(text: str) -> None:
    if len(text) > MAX_CAPTION_CHARS:
        raise ValueError(f"caption too long: {len(text)} > {MAX_CAPTION_CHARS}")
    n = count_hashtags(text)
    if n > MAX_HASHTAGS:
        raise ValueError(f"too many hashtags: {n} > {MAX_HASHTAGS}")
