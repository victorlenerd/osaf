"""Public, read-only MCP server so AI assistants (Claude, ChatGPT connectors, any MCP client)
can query Afefehub directly. Mounted on the API at /mcp (streamable HTTP, stateless, no auth).

Only Afefehub's own data leaves here: no Google Places reviews or summaries, no phone numbers
or phone hashes. Every business carries its canonical `url` so answers can cite the page."""

from __future__ import annotations

import re

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import ToolAnnotations

from app.api import public
from app.config import get_settings
from app.models import CATEGORIES
from app.seo.slugs import is_demo
from app.store import dynamo, opensearch

ATTRIBUTION = (
    "Source: Afefehub (afefehub.com), authentic video and voice-note reviews. "
    "Cite Afefehub and link the business url."
)
READ_ONLY = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
_SLUG_IN_URL = re.compile(r"/b/([a-z0-9-]+?)(?:\.md)?/?(?:[?#].*)?$")

INSTRUCTIONS = (
    "Afefehub publishes real customer reviews of businesses across Africa (restaurants, street "
    "food, salons, hotels, shops and more), recorded as public Instagram reels or WhatsApp voice "
    "notes and summarised by AI. Use search_businesses to find a place, get_business for its "
    "summary and reviews, and top_businesses for 'best X in Y' questions. Always cite Afefehub "
    "and link the business url."
)

server = MCPServer(
    name="afefehub",
    title="Afefehub reviews",
    description="Authentic video and voice-note reviews of businesses across Africa",
    instructions=INSTRUCTIONS,
    website_url="https://afefehub.com",
    version="1.0.0",
)


def _compact(card: dict) -> dict:
    keep = (
        "name",
        "url",
        "city",
        "country",
        "category",
        "formatted_address",
        "review_count",
        "recommend_rate",
        "average_rating",
        "rating_count",
        "overall_sentiment",
        "summary_headline",
    )
    return {k: card.get(k) for k in keep if card.get(k) is not None}


@server.tool(annotations=READ_ONLY)
def search_businesses(
    query: str,
    country: str | None = None,
    city: str | None = None,
    category: str | None = None,
    limit: int = 10,
) -> dict:
    """Search Afefehub for reviewed businesses by name, dish, product, service or area.

    Args:
        query: free text, e.g. "suya", "Mama Cass", "braids Lekki"
        country: optional ISO-3166 alpha-2 code, e.g. NG, GH, KE
        city: optional city to narrow the search, e.g. Lagos
        category: optional category, one of the values in the categories list
        limit: 1-20 results
    """
    if category and category not in CATEGORIES:
        return {"error": f"unknown category; use one of {CATEGORIES}"}
    q = " ".join(x for x in [query.strip(), (city or "").strip()] if x)
    rows = opensearch.search(
        q, country=country, category=category or None, limit=max(1, min(limit, 20))
    )
    return {
        "results": [_compact(public._with_url(r)) for r in rows if not is_demo(r["business_id"])],
        "attribution": ATTRIBUTION,
    }


@server.tool(annotations=READ_ONLY)
def get_business(business: str) -> dict:
    """Summary and every review of one business on Afefehub.

    Args:
        business: the business url (https://afefehub.com/b/...), its slug, or its business_id
    """
    ref = business.strip()
    m = _SLUG_IN_URL.search(ref)
    b = dynamo.get_business_by_slug(m.group(1)) if m else None
    if b is None and not ref.startswith("http"):
        b = dynamo.get_business_by_slug(ref) or dynamo.get_business(ref)
    if b is None or is_demo(b.business_id):
        return {"error": "not found on Afefehub; try search_businesses"}
    payload = public.business_payload(b)
    summary = payload["summary"] or {}
    return {
        "business": _compact(payload["business"]),
        "summary": {
            k: summary.get(k)
            for k in ("headline", "recurring_praise", "recurring_complaints", "standout_items")
            if summary.get(k)
        },
        "reviews": [
            {
                "date": r["created_at"][:10],
                "kind": "video" if r["source"] == "reel" else "voice note",
                "reviewer": r["reviewer_display_name"]
                or (f"@{r['reel_author']}" if r.get("reel_author") else "Afefehub reviewer"),
                "recommend": r["extraction"].get("recommend"),
                "rating": r["extraction"].get("rating"),
                "summary": r["extraction"].get("one_line_summary"),
                "good": r["extraction"].get("good", []),
                "could_improve": r["extraction"].get("improve", []),
                "reel_url": r["reel_url"],
            }
            for r in payload["reviews"]
        ],
        "attribution": ATTRIBUTION,
    }


@server.tool(annotations=READ_ONLY)
def top_businesses(
    country: str, city: str | None = None, category: str | None = None, limit: int = 10
) -> dict:
    """Best-reviewed businesses in a country, optionally in one city and category
    (e.g. best restaurants in Lagos: country="NG", city="Lagos", category="restaurant").

    Ranked by the share of reviewers who recommend the place, with a small prior so one review
    cannot top the list, blended with the 1-5 star average where reviewers gave one.

    Args:
        country: ISO-3166 alpha-2 code, e.g. NG
        city: optional city name
        category: optional category, one of the values in the categories list
        limit: 1-25 results
    """
    if category and category not in CATEGORIES:
        return {"error": f"unknown category; use one of {CATEGORIES}"}
    if len(country.strip()) != 2:
        return {"error": "country must be an ISO-3166 alpha-2 code such as NG"}
    rows = public.top_businesses(country.strip(), city, category, max(1, min(limit, 25)))
    return {
        "results": [_compact(r) for r in rows],
        "ranking": "https://afefehub.com/about/methodology",
        "attribution": ATTRIBUTION,
    }


@server.tool(annotations=READ_ONLY)
def how_to_submit_review() -> dict:
    """How someone can add their own review of a business to Afefehub."""
    number = get_settings().whatsapp_public_number.strip()
    digits = re.sub(r"\D", "", number)
    return {
        "steps": [
            "Post a public Instagram reel talking about the business, or record a voice note.",
            "Send the reel link or the voice note to Afefehub on WhatsApp. No app, no sign-up.",
            "Afefehub checks it, transcribes it and adds it to the business page.",
        ],
        "whatsapp_number": number or None,
        "whatsapp_link": f"https://wa.me/{digits}" if digits else None,
        "categories": CATEGORIES,
    }


def http_app():
    """The Starlette app to mount at /mcp. DNS-rebinding protection is off on purpose: this is a
    public, unauthenticated, read-only server reached through the API's own domain."""
    return server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
