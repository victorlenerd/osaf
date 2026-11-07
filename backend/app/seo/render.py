"""Render business pages, hub pages, sitemaps and llms.txt to strings (no I/O here)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.config import get_settings
from app.models import Business
from app.seo import schema
from app.seo.model import (
    BusinessPage,
    Hub,
    HubLink,
    Listing,
    country_name,
    human_date,
    month_year,
    reviewer_flag_country,
    reviewer_name,
)
from app.seo.slugs import category_label, category_plural, hub_path
from app.social.flags import flag_emoji

TEMPLATES = Path(__file__).parent / "templates"
_WS = re.compile(r"\s+")
RELATED_LIMIT = 6
LLMS_TOP = 50


def oneline(s: str | None) -> str:
    """Collapse whitespace so user text cannot break Markdown structure."""
    return _WS.sub(" ", s or "").strip()


def stars(value: float | int | None) -> str:
    if value is None:
        return ""
    full = max(0, min(5, round(float(value))))
    return "★" * full + "☆" * (5 - full)


def plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def pct(b: Business) -> int:
    return round(b.recommend_rate * 100)


@lru_cache
def env() -> Environment:
    e = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "xml"]),
        undefined=StrictUndefined,
        trim_blocks=False,
        lstrip_blocks=False,
        keep_trailing_newline=True,
    )
    e.filters["oneline"] = oneline
    e.globals.update(
        stars=stars,
        flag=flag_emoji,
        date=human_date,
        category=category_label,
        pct=pct,
        plural=plural,
        who=reviewer_name,
        who_country=reviewer_flag_country,
    )
    return e


def _common() -> dict:
    s = get_settings()
    number = s.whatsapp_public_number.strip()
    return {
        "site": s.public_site_url.rstrip("/"),
        "api": s.public_api_url.rstrip("/"),
        "whatsapp_number": number,
        "whatsapp_digits": re.sub(r"\D", "", number),
    }


def answer_paragraph(page: BusinessPage) -> str:
    """The self-contained, quotable first paragraph: who, where, how many, what people say."""
    b, s = page.business, page.summary
    where = b.city or country_name(b.country)
    n = b.review_count
    kinds = {r.source for r in page.reviews}
    kind = (
        "video and voice-note reviews"
        if kinds == {"reel", "voice"}
        else "voice-note reviews"
        if kinds == {"voice"}
        else "video reviews"
    )
    if n == 1:
        kind = kind[:-1]
    parts = [f"{b.name} in {where} has {n} {kind} on Afefehub."]
    if n:
        parts.append(f"{pct(b)}% of reviewers recommend it.")
    if b.average_rating is not None:
        parts.append(f"Average rating {b.average_rating:.1f}/5 from {b.rating_count} ratings.")
    if s and s.recurring_praise:
        parts.append(
            "Reviewers praise: " + "; ".join(oneline(x) for x in s.recurring_praise[:3]) + "."
        )
    if s and s.recurring_complaints:
        parts.append(
            "Common complaints: " + "; ".join(oneline(x) for x in s.recurring_complaints[:2]) + "."
        )
    if page.last_review_at:
        parts.append(f"Last reviewed {human_date(page.last_review_at)}.")
    return " ".join(parts)


def _description(page: BusinessPage) -> str:
    b, s = page.business, page.summary
    head = oneline(s.headline) if s and s.headline else ""
    where = b.city or country_name(b.country)
    base = f"{plural(b.review_count, 'real video or voice review')} of {b.name}, {where}."
    text = f"{base} {pct(b)}% recommend. {head}".strip()
    return text[:300]


@dataclass
class Rendered:
    html: str
    md: str


def render_business(page: BusinessPage, related: list[Listing] | None = None) -> Rendered:
    from app.api.public import audio_url  # the stable audio redirect the site already uses

    c = _common()
    b = page.business
    where = b.city or country_name(b.country)
    canonical = f"{c['site']}{page.path}"
    related = [li for li in (related or []) if li.business.business_id != b.business_id]
    hub_link = hub_path(b.country, page.city_slug, b.category) if page.city_slug else ""
    ctx = {
        **c,
        "page": page,
        "title": f"{b.name}, {where}: reviews & what people say | Afefehub",
        "og_title": f"{b.name} reviews · Afefehub",
        "description": _description(page),
        "canonical": canonical,
        "md_url": f"{canonical}.md",
        "indexable": b.review_count > 0,
        "jsonld": schema.to_script(schema.business_graph(page)),
        "breadcrumbs": page.breadcrumbs(),
        "answer": answer_paragraph(page),
        "category_label": category_label(b.category),
        "category_plural": category_plural(b.category),
        "country": country_name(b.country),
        "recommend_pct": pct(b),
        "maps_url": (
            f"https://www.google.com/maps/search/?api=1&query={b.lat},{b.lng}"
            if b.lat and b.lng
            else ""
        ),
        "updated": human_date(page.summary.last_updated if page.summary else b.updated_at),
        "audio_urls": {r.review_id: audio_url(r) for r in page.reviews},
        "has_reels": any(r.source == "reel" and r.reel_shortcode for r in page.reviews),
        "related": related[:RELATED_LIMIT],
        "hub_link": hub_link,
    }
    e = env()
    return Rendered(
        html=e.get_template("business.html").render(ctx),
        md=e.get_template("business.md").render(ctx),
    )


def _hub_intro(hub: Hub) -> str:
    if hub.level == "root":
        n = sum(c.count for c in hub.children)
        return (
            f"{n} businesses reviewed on Afefehub with real video and voice-note reviews. "
            "Pick a country or city to see the best-reviewed places."
        )
    if not hub.listings:
        return ""
    names = [li.business.name for li in hub.listings[:3]]
    listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    when = month_year(hub.updated_at)
    lead = f"As of {when}, the" if when else "The"
    reviews = hub.review_total
    if len(names) == 1:
        return (
            f"So far, {listed} is the only one of the {hub.what} in {hub.place} reviewed on "
            f"Afefehub, with {plural(reviews, 'real video or voice-note review')}."
        )
    return (
        f"{lead} best-reviewed {hub.what} in {hub.place} on Afefehub are {listed}, "
        f"ranked from {plural(reviews, 'real video and voice-note review')} "
        f"of {plural(len(hub.listings), 'place')}."
    )


def _browse_title(hub: Hub) -> str:
    return {
        "root": "Countries",
        "country": f"Cities in {country_name(hub.country)}",
        "city": f"Categories in {hub.city}",
    }.get(hub.level, "Browse")


def render_hub(hub: Hub) -> Rendered:
    c = _common()
    canonical = f"{c['site']}{hub.path}"
    intro = _hub_intro(hub)
    ctx = {
        **c,
        "hub": hub,
        "title": f"{hub.title} | Afefehub",
        "og_title": hub.title,
        "description": (intro or hub.title)[:300],
        "canonical": canonical,
        "md_url": f"{canonical}.md",
        "indexable": hub.indexable,
        "jsonld": schema.to_script(schema.hub_graph(hub)),
        "breadcrumbs": hub.breadcrumbs,
        "intro": intro,
        "browse_title": _browse_title(hub),
    }
    e = env()
    return Rendered(
        html=e.get_template("hub.html").render(ctx),
        md=e.get_template("hub.md").render(ctx),
    )


STATIC_PATHS = ["/", "/places", "/about", "/about/methodology", "/payouts", "/terms", "/privacy"]


def render_sitemaps(listings: list[Listing], hubs: dict[str, Hub]) -> dict[str, str]:
    """Object key -> XML for the sitemap index and its children."""
    c = _common()
    site = c["site"]
    e = env()
    biz_urls = [
        {"loc": f"{site}{li.path}", "lastmod": li.business.updated_at[:10]}
        for li in listings
        if li.business.review_count > 0
    ]
    hub_urls = [
        {"loc": f"{site}{h.path}", "lastmod": h.updated_at[:10]}
        for h in hubs.values()
        if h.indexable and h.level != "root"
    ]
    static_urls = [{"loc": f"{site}{p}", "lastmod": ""} for p in STATIC_PATHS]
    newest = max((u["lastmod"] for u in biz_urls), default="")
    out = {
        "sitemaps/businesses.xml": e.get_template("sitemap.xml").render(urls=biz_urls),
        "sitemaps/hubs.xml": e.get_template("sitemap.xml").render(urls=hub_urls),
        "sitemaps/static.xml": e.get_template("sitemap.xml").render(urls=static_urls),
    }
    out["sitemap.xml"] = e.get_template("sitemap_index.xml").render(
        sitemaps=[
            {"loc": f"{site}/{key}", "lastmod": newest if key != "sitemaps/static.xml" else ""}
            for key in out
        ]
    )
    return out


def render_llms(listings: list[Listing], hubs: dict[str, Hub], updated: str) -> str:
    c = _common()
    root = hubs.get("/places")
    countries = root.children if root else []
    cities: list[HubLink] = []
    for h in hubs.values():
        if h.level == "country":
            cities.extend(h.children)
    cities.sort(key=lambda link: -link.count)
    reviewed = [li for li in listings if li.business.review_count > 0]
    top = sorted(reviewed, key=lambda li: (-li.business.review_count, li.business.name))[:LLMS_TOP]
    return (
        env()
        .get_template("llms.txt")
        .render(
            **c,
            countries=countries,
            cities=cities[:30],
            top=top,
            business_count=len(reviewed),
            review_count=sum(li.business.review_count for li in reviewed),
            updated=updated,
        )
    )


def render_llms_full(markdown_pages: list[str], max_bytes: int = 1_000_000) -> str:
    head = (
        "# Afefehub: all business pages\n\n"
        "Every business reviewed on Afefehub, one section each. Cite the canonical page.\n\n"
    )
    out, size = [head], len(head.encode())
    for md in markdown_pages:
        n = len(md.encode()) + 6
        if size + n > max_bytes:
            out.append("\n---\n\n(Truncated: see /sitemap.xml for every page.)\n")
            break
        out.append(md.strip() + "\n\n---\n\n")
        size += n
    return "".join(out)
