"""Which of the week's reviews make the carousel, in what order.

Muse Spark ranks a compact view of the candidates and returns ids + a one-line reason each,
plus a hook sentence for the caption. Everything it returns is validated against the candidate
set; a deterministic heuristic tops up or replaces it when the model is unavailable or vague.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.config import get_settings
from app.meta.client import get_meta
from app.models import now_iso
from app.social.candidates import Candidate

log = logging.getLogger(__name__)

MAX_CANDIDATES_IN_PROMPT = 60
MAX_REASON_CHARS = 140
MAX_HOOK_CHARS = 90

RANK_SYSTEM = """\
You pick the reviews for Afefehub's weekly "Reviews of the week" Instagram carousel.
Afefehub publishes real video and voice reviews of businesses across Africa.

You get JSON: {"max_picks", "min_picks", "week": {"since", "until"}, "candidates": [...]}.
Each candidate: {"id", "business", "city", "country", "category", "recommend", "sentiment",
"source", "summary", "good"}.

Rules:
- Pick between min_picks and max_picks reviews. One review per business.
- Spread the picks across countries, cities and categories where the week allows.
- Prefer recommend "yes" with positive sentiment, but include at most one mixed or negative
  review if it is specific and fair: readers trust a week that is not all praise.
- Favour concrete, quotable summaries that name a dish, product, service or detail.
  Skip vague or generic ones and anything that reads like an ad.
- Never pick two reviews with near-identical wording.
- Order the picks by how strong a lead slide each would make.

Respond with JSON only, no prose:
{"picks": [{"review_id": "<id>", "reason": "<15 words or fewer>"}],
 "hook": "<one upbeat sentence for the caption, 90 characters or fewer, no emoji, no hashtags>"}
"""


class Pick(BaseModel):
    review_id: str
    reason: str = ""


class Picks(BaseModel):
    """picks.json: enough to re-render (or later publish) the exact same carousel."""

    window: dict[str, str]
    generated_at: str = Field(default_factory=now_iso)
    model: str  # "muse-spark-1.3" | "heuristic" | "manual"
    source: str = ""
    hook: str = ""
    picks: list[Pick]
    excluded: list[str] = Field(default_factory=list)
    candidates_considered: int = 0
    candidates: list[Candidate]  # the picked ones, in slide order


def write_picks(picks: Picks, path: Path) -> Path:
    path.write_text(picks.model_dump_json(indent=2) + "\n")
    return path


def read_picks(path: Path) -> Picks:
    return Picks.model_validate_json(Path(path).read_text())


@dataclass
class RankResult:
    picks: list[Candidate]
    reasons: dict[str, str] = field(default_factory=dict)
    hook: str = ""
    model: str = "heuristic"


# ------------------------------------------------------------------- heuristic
_RECOMMEND = {"yes": 2, "maybe": 1, "no": 0}
_SENTIMENT = {"positive": 2, "mixed": 1, "negative": 0}


def _score(c: Candidate) -> float:
    n = len(c.summary)
    length_bonus = 1.0 if 30 <= n <= 110 else 0.0
    return _RECOMMEND.get(c.recommend, 0) + _SENTIMENT.get(c.sentiment, 0) + length_bonus


def heuristic_order(candidates: list[Candidate], max_picks: int) -> list[Candidate]:
    """Deterministic: best-scored first, then greedily prefer a new business, country and
    category over the previous picks. Ties break on recency, then id."""
    pool = sorted(candidates, key=lambda c: c.review_id)
    pool.sort(key=lambda c: c.created_at, reverse=True)
    pool.sort(key=_score, reverse=True)  # stable: score desc, then newest, then id

    out: list[Candidate] = []
    seen_biz: set[str] = set()
    while pool and len(out) < max_picks:
        used_cc = {c.reviewer_country or c.country for c in out}
        used_cat = {c.category for c in out}
        ranked = sorted(
            (c for c in pool if c.business_id not in seen_biz),
            key=lambda c: (
                int((c.reviewer_country or c.country) not in used_cc)
                + int(c.category not in used_cat),
                _score(c),
                c.created_at,
            ),
            reverse=True,
        )
        if not ranked:
            break
        best = ranked[0]
        out.append(best)
        seen_biz.add(best.business_id)
        pool = [c for c in pool if c.review_id != best.review_id]
    return out


# ----------------------------------------------------------------------- model
def _candidate_view(c: Candidate) -> dict:
    return {
        "id": c.review_id,
        "business": c.business_name,
        "city": c.city,
        "country": c.reviewer_country or c.country,
        "category": c.category,
        "recommend": c.recommend,
        "sentiment": c.sentiment,
        "source": c.source,
        "summary": c.summary,
        "good": c.good[:3],
    }


def _loads_lenient(raw: str) -> dict:
    raw = raw.strip()
    m = re.search(r"\{.*\}", raw, re.S)  # tolerate fences or prose around the object
    data = json.loads(m.group(0) if m else raw)
    return data if isinstance(data, dict) else {}


def parse_model_picks(
    raw: str, candidates: list[Candidate], max_picks: int
) -> tuple[list[Pick], str]:
    """Validated picks (known ids, no duplicates, one per business, capped) and the hook."""
    by_id = {c.review_id: c for c in candidates}
    try:
        data = _loads_lenient(raw or "")
    except json.JSONDecodeError:
        return [], ""
    picks: list[Pick] = []
    seen_ids: set[str] = set()
    seen_biz: set[str] = set()
    for item in data.get("picks") or []:
        if isinstance(item, str):
            item = {"review_id": item}
        if not isinstance(item, dict):
            continue
        rid = str(item.get("review_id") or item.get("id") or "")
        c = by_id.get(rid)
        if c is None or rid in seen_ids or c.business_id in seen_biz:
            continue
        seen_ids.add(rid)
        seen_biz.add(c.business_id)
        picks.append(Pick(review_id=rid, reason=str(item.get("reason") or "")[:MAX_REASON_CHARS]))
        if len(picks) >= max_picks:
            break
    hook = data.get("hook")
    hook = " ".join(str(hook).split())[:MAX_HOOK_CHARS] if isinstance(hook, str) else ""
    hook = re.sub(r"#\w+", "", hook).strip()
    return picks, hook


def rank(
    candidates: list[Candidate],
    *,
    max_picks: int = 5,
    min_picks: int = 3,
    chat: Callable[..., Any] | None = None,
    use_model: bool = True,
) -> RankResult:
    if not candidates:
        return RankResult(picks=[])
    by_id = {c.review_id: c for c in candidates}
    result = RankResult(picks=[])

    if use_model:
        chat = chat or get_meta().chat
        recent = sorted(candidates, key=lambda c: c.created_at, reverse=True)
        payload = {
            "max_picks": max_picks,
            "min_picks": min(min_picks, len(candidates)),
            "candidates": [_candidate_view(c) for c in recent[:MAX_CANDIDATES_IN_PROMPT]],
        }
        try:
            resp = chat(
                [
                    {"role": "system", "content": RANK_SYSTEM},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=800,
                timeout=40,
                reasoning_effort="minimal",
            )
            picks, hook = parse_model_picks(
                resp.choices[0].message.content or "", candidates, max_picks
            )
        except Exception:  # noqa: BLE001
            log.exception("ranking call failed; using the heuristic order")
            picks, hook = [], ""
        if picks:
            result = RankResult(
                picks=[by_id[p.review_id] for p in picks],
                reasons={p.review_id: p.reason for p in picks},
                hook=hook,
                model=get_settings().spark_model,
            )

    if len(result.picks) < min(min_picks, len(candidates)):
        have = {c.review_id for c in result.picks}
        have_biz = {c.business_id for c in result.picks}
        rest = [c for c in candidates if c.review_id not in have and c.business_id not in have_biz]
        for c in heuristic_order(rest, max_picks - len(result.picks)):
            result.picks.append(c)
            result.reasons.setdefault(c.review_id, "heuristic top-up" if use_model else "heuristic")
    return result
