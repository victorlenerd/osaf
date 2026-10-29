"""Muse Spark 1.3 tool loop that turns a transcript into a ReviewExtraction.

Each WhatsApp turn re-runs this from the persisted Submission (stateless reconstruction): the
model gets the transcript, fields collected so far, the Q/A log and the reviewer's latest answer,
then loops over tool calls until it asks a question, finalizes, or rejects.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.agent import places
from app.agent.prompts import EXTRACTION_SYSTEM, build_extraction_context
from app.agent.tools import ALL_TOOLS, TOOLS_NO_ASK
from app.config import get_settings
from app.meta.client import get_meta
from app.models import Conversation, PlaceCandidate, ReviewExtraction, Submission

log = logging.getLogger(__name__)

MAX_ITERATIONS = 8
MAX_SEARCHES_PER_TURN = 4
BUSINESS_CONF_MIN = 0.7


class ExtractionOutcome(BaseModel):
    kind: Literal["ask", "final", "reject"]
    question: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    candidates_shown: list[str] = Field(default_factory=list)
    extraction: ReviewExtraction | None = None
    reason: str | None = None
    place_candidates: list[PlaceCandidate] = Field(default_factory=list)
    collected: dict = Field(default_factory=dict)
    trace: list[dict] = Field(default_factory=list)


ChatFn = Callable[..., Any]


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:40] or "unknown"


def run_extraction_turn(
    sub: Submission,
    conv: Conversation,
    latest_answer: str | None,
    *,
    chat: ChatFn | None = None,
    search_fn: Callable[..., list[PlaceCandidate]] | None = None,
) -> ExtractionOutcome:
    settings = get_settings()
    chat = chat or get_meta().chat
    search_fn = search_fn or places.search_places

    rounds_left = max(0, settings.max_clarification_rounds - sub.clarification_rounds)
    tools = ALL_TOOLS if rounds_left > 0 else TOOLS_NO_ASK
    messages: list[dict] = [
        {"role": "system", "content": EXTRACTION_SYSTEM.format(rounds_left=rounds_left)},
        {"role": "user", "content": build_extraction_context(sub, conv, latest_answer)},
    ]
    trace: list[dict] = []
    known_candidates: dict[str, PlaceCandidate] = {c.place_id: c for c in sub.place_candidates}
    searches_this_turn = 0
    total_searches = int((sub.collected or {}).get("_search_attempts", 0))
    last_results: list[PlaceCandidate] = list(sub.place_candidates)
    finalize_retry_used = False
    plain_text_retry_used = False

    for _ in range(MAX_ITERATIONS):
        resp = chat(messages, tools=tools, tool_choice="auto", temperature=0.1, max_tokens=1500)
        msg = resp.choices[0].message
        tool_calls = list(msg.tool_calls or [])
        trace.append(
            {
                "assistant": msg.content,
                "tool_calls": [
                    {"name": tc.function.name, "args": tc.function.arguments} for tc in tool_calls
                ],
            }
        )
        if not tool_calls:
            text = (msg.content or "").strip()
            if text.upper().startswith("REJECT:"):
                return ExtractionOutcome(
                    kind="reject", reason=text[7:].strip() or "not a business review", trace=trace
                )
            if plain_text_retry_used:
                return ExtractionOutcome(
                    kind="reject", reason="agent produced no structured result", trace=trace
                )
            plain_text_retry_used = True
            messages.append({"role": "assistant", "content": text})
            messages.append(
                {
                    "role": "user",
                    "content": "You must respond with a tool call (search_places, ask_user or "
                    "finalize_review) or a line starting with REJECT:.",
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

            if name == "search_places":
                if searches_this_turn >= MAX_SEARCHES_PER_TURN:
                    result: Any = {"error": "search limit reached; ask the user or finalize"}
                else:
                    searches_this_turn += 1
                    total_searches += 1
                    bias = args.get("location_bias") or {}
                    try:
                        found = search_fn(
                            args.get("query", ""),
                            args.get("region_code") or conv.profile_country or "",
                            lat=bias.get("lat"),
                            lng=bias.get("lng"),
                            radius_m=int(bias.get("radius_m") or 20000),
                        )
                    except Exception as e:  # noqa: BLE001
                        log.exception("places search failed")
                        found = []
                        result = {"error": f"search failed: {e}"}
                    else:
                        last_results = found
                        for c in found:
                            known_candidates[c.place_id] = c
                        result = {"results": [c.model_dump() for c in found]}
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)}
                )
                continue

            if name == "ask_user":
                if rounds_left <= 0:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(
                                {"error": "no questions left; finalize or REJECT"}
                            ),
                        }
                    )
                    continue
                shown_ids = [str(x) for x in args.get("candidates_shown") or []]
                shown = [known_candidates[i] for i in shown_ids if i in known_candidates]
                if not shown and last_results:
                    shown = last_results[:5]
                return ExtractionOutcome(
                    kind="ask",
                    question=(args.get("question") or "Could you tell me more?").strip()[:900],
                    missing_fields=list(args.get("missing_fields") or []),
                    candidates_shown=[c.place_id for c in shown],
                    place_candidates=shown,
                    collected={**(sub.collected or {}), "_search_attempts": total_searches},
                    trace=trace,
                )

            if name == "finalize_review":
                problems = _validate_finalize(args, known_candidates, total_searches)
                if problems:
                    if finalize_retry_used:
                        if rounds_left > 0:
                            # Turn the validation problem into a question for the reviewer.
                            return ExtractionOutcome(
                                kind="ask",
                                question=_fallback_question(args, last_results),
                                missing_fields=["business"],
                                candidates_shown=[c.place_id for c in last_results[:3]],
                                place_candidates=last_results[:3],
                                collected={
                                    **(sub.collected or {}),
                                    "_search_attempts": total_searches,
                                },
                                trace=trace,
                            )
                        return ExtractionOutcome(
                            kind="reject", reason="; ".join(problems), trace=trace
                        )
                    finalize_retry_used = True
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps({"error": "invalid", "problems": problems}),
                        }
                    )
                    continue
                ext = _coerce(args, known_candidates)
                return ExtractionOutcome(
                    kind="final",
                    extraction=ext,
                    collected={**(sub.collected or {}), "_search_attempts": total_searches},
                    trace=trace,
                )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps({"error": f"unknown tool {name}"}),
                }
            )

    return ExtractionOutcome(kind="reject", reason="agent did not converge", trace=trace)


def _validate_finalize(
    args: dict, known: dict[str, PlaceCandidate], total_searches: int
) -> list[str]:
    problems: list[str] = []
    biz = args.get("business") or {}
    pid = str(biz.get("place_id") or "")
    conf = (args.get("confidence") or {}).get("business")
    if not pid:
        problems.append("business.place_id missing")
    elif pid.startswith("afefe:"):
        if total_searches < 2:
            problems.append("afefe: ids are only allowed after at least two search_places calls")
        if not biz.get("name"):
            problems.append("business.name required for user-sourced business")
    elif pid not in known:
        problems.append("business.place_id must come from a search_places result")
    if conf is not None and float(conf) < BUSINESS_CONF_MIN and not pid.startswith("afefe:"):
        problems.append(f"business confidence {conf} < {BUSINESS_CONF_MIN}; ask the reviewer")
    try:
        _coerce(args, known)
    except ValidationError as e:
        problems.append(f"schema: {e.errors()[0].get('msg')} at {e.errors()[0].get('loc')}")
    return problems


def _coerce(args: dict, known: dict[str, PlaceCandidate]) -> ReviewExtraction:
    biz = dict(args.get("business") or {})
    pid = str(biz.get("place_id") or "")
    if pid in known:
        c = known[pid]
        biz = {
            "place_id": c.place_id,
            "name": c.name or biz.get("name"),
            "formatted_address": c.formatted_address or biz.get("formatted_address"),
            "lat": c.lat,
            "lng": c.lng,
            "country": (c.country or biz.get("country") or "").upper(),
            "city": c.city or biz.get("city"),
            "primary_type": c.primary_type,
            "source": "google",
        }
    else:
        biz["source"] = "user"
        biz["country"] = (biz.get("country") or "").upper()
        if not pid.startswith("afefe:"):
            biz["place_id"] = f"afefe:{_slug(biz.get('name', ''))}-{_slug(biz.get('city', ''))}"
    args = {**args, "business": biz}
    args["visit"] = {k: v for k, v in (args.get("visit") or {}).items() if v}
    args["keywords"] = [k for k in (args.get("keywords") or []) if isinstance(k, str)][:10]
    args["good"] = [g for g in (args.get("good") or []) if isinstance(g, str)][:6]
    args["improve"] = [g for g in (args.get("improve") or []) if isinstance(g, str)][:6]
    return ReviewExtraction(**args)


def _fallback_question(args: dict, candidates: list[PlaceCandidate]) -> str:
    said = (args.get("business_name_as_said") or "the business").strip()
    if candidates:
        opts = "\n".join(
            f"{i + 1}. {c.name} — {c.formatted_address}" for i, c in enumerate(candidates[:3])
        )
        return (
            f"I want to be sure I tag the right place for {said}. Which one is it?\n{opts}\n"
            "Reply with the number, or tell me the street/area if none match."
        )
    return (
        f"I couldn't find {said} on the map. Which city and street/area is it in? "
        "Any landmark helps."
    )
