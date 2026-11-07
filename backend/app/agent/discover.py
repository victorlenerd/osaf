"""Vendor discovery over WhatsApp: a Muse Spark tool loop that answers "where can I get good suya
in Lekki?" from Afefehub's reviewed businesses, falling back to (clearly labelled, unreviewed)
Google Places when Afefehub has nothing.

Like the extraction agent, a turn is stateless: the short chat history, the numbered options shown
last time and the shared location are rebuilt from the Conversation each time.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import quote

from pydantic import BaseModel, Field

from app.agent import places
from app.agent.prompts import (
    DISCOVERY_SYSTEM,
    GOOGLE_RULE_OFF,
    GOOGLE_RULE_ON,
    INTENT_SYSTEM,
    build_discovery_context,
)
from app.agent.tools import DISCOVERY_TOOLS, DISCOVERY_TOOLS_NO_GOOGLE
from app.config import get_settings
from app.countries import country_code
from app.meta.client import get_meta
from app.models import (
    CATEGORIES,
    ChatTurn,
    Conversation,
    DiscoverySession,
    PlaceCandidate,
    ShownVendor,
    now_iso,
)

log = logging.getLogger(__name__)

MAX_ITERATIONS = 5
MAX_SEARCHES_PER_TURN = 3
MAX_GOOGLE_PER_TURN = 1
MAX_TURNS_KEPT = 6
MAX_TURN_CHARS = 500
MAX_REPLY_CHARS = 1500
DEFAULT_RADIUS_KM = 5.0

FALLBACK_MSG = (
    "Sorry, I couldn't work that one out. Tell me what you're looking for and where, e.g. "
    "*best suya in Lekki* or *barber in Wuse 2*, or share your location 📍."
)
NO_MATCH_MSG = (
    "I couldn't find a reviewed place for that on Afefehub yet. Know a good one? Send me a "
    "voice note about your visit and it becomes the first review 🙏"
)

ChatFn = Callable[..., Any]


class DiscoveryOutcome(BaseModel):
    message: str
    session: DiscoverySession
    searched: bool = False
    trace: list[dict] = Field(default_factory=list)


# ------------------------------------------------------------------------- helpers
def _age_seconds(iso: str) -> float:
    return (datetime.now(UTC) - datetime.fromisoformat(iso.replace("Z", "+00:00"))).total_seconds()


def live_session(conv: Conversation) -> DiscoverySession | None:
    """The discovery chat if it was active recently, else None (a stale one is forgotten)."""
    s = conv.discovery
    if s is None or _age_seconds(s.updated_at) > get_settings().discovery_session_seconds:
        return None
    return s


def live_location(conv: Conversation) -> dict | None:
    loc = conv.last_location
    if loc is None or _age_seconds(loc.at) > get_settings().discovery_session_seconds:
        return None
    return {"lat": loc.lat, "lng": loc.lng}


def vendor_url(business_id: str) -> str:
    base = get_settings().public_site_url.rstrip("/")
    return f"{base}/business?id={quote(business_id, safe='')}"


def _vendor_row(r: dict) -> dict:
    """A search hit as the model sees it: no score, no raw coordinates, a ready-made link."""
    row = {
        "business_id": r["business_id"],
        "name": r["name"],
        "area": r.get("formatted_address") or r.get("city") or "",
        "category": r.get("category"),
        "review_count": r.get("review_count", 0),
        "recommend_pct": round(100 * float(r.get("recommend_rate") or 0)),
        "headline": r.get("summary_headline"),
        "url": vendor_url(r["business_id"]),
    }
    if r.get("distance_km") is not None:
        row["distance_km"] = r["distance_km"]
    return row


def format_google_results(places_found: list[PlaceCandidate], *, limit: int = 3) -> str:
    """A plain numbered list of Google listings, used when the agent did not finish a reply."""
    lines = ["Nothing reviewed on Afefehub for that yet, but Google lists these:"]
    for i, c in enumerate(places_found[:limit], start=1):
        lines.append(f"\n{i}. *{c.name}*, {c.formatted_address}\n(not yet reviewed on Afefehub)")
    lines.append(
        "\nBeen to one? Send me a voice note about your visit and it becomes the first review."
    )
    return "\n".join(lines)


def format_results(rows: list[dict], *, limit: int = 3) -> str:
    """A plain numbered list of search hits, used when the agent cannot run or did not finish."""
    if not rows:
        return NO_MATCH_MSG
    lines = ["Here's what Afefehub reviewers recommend:"]
    for i, r in enumerate(rows[:limit], start=1):
        v = r if "url" in r else _vendor_row(r)
        reviews = f"{v['review_count']} review{'s' if v['review_count'] != 1 else ''}"
        lines.append(
            f"\n{i}. *{v['name']}*, {v['area']}\n"
            f"👍 {v['recommend_pct']}% recommend ({reviews})"
            + (f"\n{v['headline']}" if v.get("headline") else "")
            + f"\n{v['url']}"
        )
    return "\n".join(lines)


def _vendor_details(business_id: str) -> dict | None:
    from app.store import dynamo

    b = dynamo.get_business(business_id)
    if b is None:
        return None
    summary = dynamo.get_summary(business_id)
    reviews = [r for r in dynamo.list_reviews(business_id, limit=20) if r.status == "published"]
    reviews.sort(key=lambda r: r.created_at, reverse=True)
    return {
        "business_id": b.business_id,
        "name": b.name,
        "area": b.formatted_address,
        "category": b.category,
        "review_count": b.review_count,
        "recommend_pct": round(100 * b.recommend_rate),
        "headline": summary.headline if summary else None,
        "praise": summary.recurring_praise if summary else [],
        "complaints": summary.recurring_complaints if summary else [],
        "standout_items": summary.standout_items if summary else [],
        "latest_reviews": [
            {
                "when": r.created_at[:10],
                "good": r.extraction.good,
                "improve": r.extraction.improve,
                "recommend": r.extraction.recommend,
            }
            for r in reviews[:3]
        ],
        "url": vendor_url(b.business_id),
    }


def _default_search(query: str, **kw) -> list[dict]:
    from app.store import opensearch

    return opensearch.search(query, **kw)


def _default_google(query: str, region: str) -> list[PlaceCandidate]:
    if not places.google_bucket.take():
        raise RuntimeError("Google lookups are busy, try again shortly")
    return places.search_places(query, region, max_results=3)


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------ the loop
def run_discovery_turn(
    conv: Conversation,
    text: str,
    *,
    chat: ChatFn | None = None,
    search_fn: Callable[..., list[dict]] | None = None,
    details_fn: Callable[[str], dict | None] | None = None,
    google_fn: Callable[[str, str], list[PlaceCandidate]] | None = None,
    remember_as: str | None = None,
) -> DiscoveryOutcome:
    """`text` is what the model reads. `remember_as` is the request to store as last_query when
    it differs, e.g. a location re-run whose text wraps the original request: storing the
    wrapper would nest it again on every new pin."""
    settings = get_settings()
    chat = chat or get_meta().chat
    search_fn = search_fn or _default_search
    details_fn = details_fn or _vendor_details
    google_fn = google_fn or _default_google
    google_on = settings.discovery_google_fallback

    prior = live_session(conv) or DiscoverySession()
    location = live_location(conv)
    messages: list[dict] = [
        {
            "role": "system",
            "content": DISCOVERY_SYSTEM.format(
                google_rule=GOOGLE_RULE_ON if google_on else GOOGLE_RULE_OFF
            ),
        },
        {
            "role": "user",
            "content": build_discovery_context(
                text=text,
                profile_country=conv.profile_country,
                profile_city=conv.profile_city,
                location=location,
                recent_turns=[t.model_dump() for t in prior.turns],
                options_shown=[v.model_dump() for v in prior.shown],
            ),
        },
    ]
    tools = DISCOVERY_TOOLS if google_on else DISCOVERY_TOOLS_NO_GOOGLE

    # Everything a reply may point at: options shown earlier plus what tools return now.
    known: dict[str, ShownVendor] = {v.id: v for v in prior.shown}
    results_this_turn: list[dict] = []
    google_this_turn: list[PlaceCandidate] = []
    trace: list[dict] = []
    searches = google_calls = 0
    searched_empty = False
    plain_text_retry_used = reply_retry_used = False

    def done(message: str, options: list[ShownVendor] | None) -> DiscoveryOutcome:
        message = message.strip()[:MAX_REPLY_CHARS]
        turns = [*prior.turns, ChatTurn(role="user", text=text[:MAX_TURN_CHARS])]
        turns.append(ChatTurn(role="assistant", text=message[:MAX_TURN_CHARS]))
        session = DiscoverySession(
            turns=turns[-MAX_TURNS_KEPT:],
            shown=options if options else prior.shown,
            last_query=(remember_as or text)[:200] if searches else prior.last_query,
            updated_at=now_iso(),
        )
        return DiscoveryOutcome(
            message=message, session=session, searched=bool(searches), trace=trace
        )

    def fallback() -> DiscoveryOutcome:
        if results_this_turn:
            rows = results_this_turn[:3]
            return done(
                format_results(rows),
                [
                    ShownVendor(n=i, id=r["business_id"], name=r["name"])
                    for i, r in enumerate(rows, start=1)
                ],
            )
        if google_this_turn:
            listed = google_this_turn[:3]
            return done(
                format_google_results(listed),
                [
                    ShownVendor(n=i, id=c.place_id, name=c.name, source="google")
                    for i, c in enumerate(listed, start=1)
                ],
            )
        return done(NO_MATCH_MSG if searched_empty else FALLBACK_MSG, None)

    for _ in range(MAX_ITERATIONS):
        resp = chat(messages, tools=tools, tool_choice="auto", temperature=0.2, max_tokens=1200)
        msg = resp.choices[0].message
        tool_calls = list(msg.tool_calls or [])
        trace.append(
            {
                "assistant": msg.content,
                "tool_calls": [tc.function.name for tc in tool_calls],
            }
        )
        if not tool_calls:
            if plain_text_retry_used:
                return fallback()
            plain_text_retry_used = True
            messages.append({"role": "assistant", "content": msg.content or ""})
            messages.append(
                {
                    "role": "user",
                    "content": "Respond with a tool call: search_vendors, get_vendor, "
                    + ("search_google " if google_on else "")
                    + "or reply.",
                }
            )
            continue

        messages.append(
            {
                "role": "assistant",
                "content": msg.content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            }
        )

        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result: Any

            if name == "search_vendors":
                if searches >= MAX_SEARCHES_PER_TURN:
                    result = {"error": "search limit reached; reply with what you have"}
                else:
                    searches += 1
                    result = _run_search(args, conv, location, search_fn)
                    rows = result.get("results")
                    if rows is not None:
                        if not rows:
                            searched_empty = True
                        for r in rows:
                            known[r["business_id"]] = ShownVendor(
                                n=0, id=r["business_id"], name=r["name"]
                            )
                            if all(x["business_id"] != r["business_id"] for x in results_this_turn):
                                results_this_turn.append(r)

            elif name == "get_vendor":
                bid = str(args.get("business_id") or "")
                if bid not in known or known[bid].source != "afefehub":
                    result = {"error": "unknown business_id; use one from search_vendors"}
                else:
                    try:
                        result = details_fn(bid) or {"error": "not found"}
                    except Exception as e:  # noqa: BLE001
                        log.exception("get_vendor failed")
                        result = {"error": f"lookup failed: {e}"}

            elif name == "search_google":
                if not google_on:
                    result = {"error": "Google lookups are off"}
                elif not searched_empty or results_this_turn:
                    result = {"error": "only allowed after search_vendors found nothing"}
                elif google_calls >= MAX_GOOGLE_PER_TURN:
                    result = {"error": "Google limit reached; reply with what you have"}
                else:
                    google_calls += 1
                    region = str(args.get("region_code") or conv.profile_country or "")
                    try:
                        found = google_fn(str(args.get("query") or text)[:200], region)
                    except Exception as e:  # noqa: BLE001
                        log.warning("discovery google lookup failed: %r", e)
                        result = {"error": "Google lookup failed"}
                    else:
                        open_now = [c for c in found if c.business_status in (None, "OPERATIONAL")]
                        for c in open_now:
                            known[c.place_id] = ShownVendor(
                                n=0, id=c.place_id, name=c.name, source="google"
                            )
                        google_this_turn.extend(open_now)
                        result = {
                            "not_reviewed_on_afefehub": True,
                            "results": [
                                {
                                    "place_id": c.place_id,
                                    "name": c.name,
                                    "address": c.formatted_address,
                                }
                                for c in open_now
                            ],
                        }

            elif name == "reply":
                message = str(args.get("message") or "").strip()
                ids = [str(x) for x in args.get("options") or []]
                unknown = [i for i in ids if i not in known]
                problems = []
                if not message:
                    problems.append("message is empty")
                if unknown:
                    problems.append(f"options not returned by any tool: {unknown}")
                if problems:
                    if reply_retry_used:
                        return fallback()
                    reply_retry_used = True
                    result = {"error": "invalid", "problems": problems}
                else:
                    options = [
                        known[i].model_copy(update={"n": n}) for n, i in enumerate(ids, start=1)
                    ]
                    return done(message, options)

            else:
                result = {"error": f"unknown tool {name}"}

            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})

    return fallback()


def _run_search(
    args: dict,
    conv: Conversation,
    location: dict | None,
    search_fn: Callable[..., list[dict]],
) -> dict:
    query = str(args.get("query") or "").strip()[:200]
    category = args.get("category") if args.get("category") in CATEGORIES else None
    city = str(args.get("city") or "").strip()[:80] or None
    country = country_code(str(args.get("country") or ""))
    near = None
    n = args.get("near") or {}
    lat, lng = _num(n.get("lat")), _num(n.get("lng"))
    if lat is not None and lng is not None:
        radius = _num(n.get("radius_km")) or DEFAULT_RADIUS_KM
        near = (lat, lng, max(0.5, min(radius, 50.0)))
    limit = int(_num(args.get("limit")) or 5)
    try:
        hits = search_fn(
            query,
            country=country,
            category=category,
            city=city,
            near=near,
            limit=max(1, min(limit, 5)),
        )
    except Exception as e:  # noqa: BLE001
        log.exception("discovery search failed")
        return {"error": f"search failed: {e}"}
    return {"results": [_vendor_row(h) for h in hits]}


# ------------------------------------------------------------------ intent check
Intent = Literal["answer", "discover"]

_NUMBER_WORDS = re.compile(
    r"^\s*(number\s+)?(\d+|one|two|three|four|five|first|second|third|fourth|fifth|"
    r"the\s+(first|second|third|fourth|fifth)(\s+one)?|none( of them)?|neither)\s*[.!]*\s*$",
    re.I,
)


def obviously_an_answer(text: str) -> bool:
    """Replies we never need a model to read: a number from a list, or a few words with no
    question mark (a business name, a street, a city)."""
    t = text.strip()
    if _NUMBER_WORDS.match(t):
        return True
    return "?" not in t and len(t.split()) <= 3


def classify_intent(
    text: str, pending_question: str | None, *, chat: ChatFn | None = None
) -> Intent:
    """Does a message sent while a review waits on the reviewer answer it, or ask for vendors?
    Any failure counts as an answer, which is how every message was read before discovery."""
    try:
        chat = chat or get_meta().chat
        resp = chat(
            [
                {"role": "system", "content": INTENT_SYSTEM},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"assistant_question": (pending_question or "")[-600:], "message": text},
                        ensure_ascii=False,
                    ),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=200,
            timeout=10,
            reasoning_effort="minimal",
        )
        raw = (resp.choices[0].message.content or "").strip()
        m = re.search(r"\{.*\}", raw, re.S)
        intent = json.loads(m.group(0) if m else raw).get("intent")
    except Exception:  # noqa: BLE001
        log.warning("intent check failed; treating the message as an answer", exc_info=True)
        return "answer"
    return "discover" if intent == "discover" else "answer"
