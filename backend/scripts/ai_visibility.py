"""Does Afefehub get cited when people ask AI assistants about businesses it covers?

Runs a fixed set of questions against search-grounded assistant APIs and records, per answer,
whether afefehub.com appears in the citations or the text. Run it weekly and compare.

    python scripts/ai_visibility.py                          # questions built from DynamoDB
    python scripts/ai_visibility.py --prompts prompts.txt    # one question per line
    python scripts/ai_visibility.py --out results.jsonl      # also append JSON lines here

Providers run only when their key is set (all optional; model names overridable):
    PERPLEXITY_API_KEY  (PERPLEXITY_MODEL, default "sonar")
    OPENAI_API_KEY      (OPENAI_SEARCH_MODEL, default "gpt-4.1-mini", Responses API web search)
    GEMINI_API_KEY      (GEMINI_MODEL, default "gemini-2.5-flash", Google Search grounding)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DOMAIN = "afefehub.com"
TIMEOUT = 90


def cited(text: str, urls: list[str]) -> dict:
    return {
        "cited": any(DOMAIN in (u or "") for u in urls),
        "mentioned": DOMAIN in (text or "").lower() or "afefehub" in (text or "").lower(),
        "afefehub_urls": sorted({u for u in urls if DOMAIN in (u or "")}),
    }


def ask_perplexity(q: str) -> tuple[str, list[str]]:
    r = httpx.post(
        "https://api.perplexity.ai/chat/completions",
        headers={"authorization": f"Bearer {os.environ['PERPLEXITY_API_KEY']}"},
        json={
            "model": os.environ.get("PERPLEXITY_MODEL", "sonar"),
            "messages": [{"role": "user", "content": q}],
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    text = data["choices"][0]["message"]["content"]
    urls = list(data.get("citations") or []) + [
        s.get("url", "") for s in data.get("search_results") or []
    ]
    return text, urls


def ask_openai(q: str) -> tuple[str, list[str]]:
    r = httpx.post(
        "https://api.openai.com/v1/responses",
        headers={"authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={
            "model": os.environ.get("OPENAI_SEARCH_MODEL", "gpt-4.1-mini"),
            "tools": [{"type": "web_search"}],
            "input": q,
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    text, urls = "", []
    for item in r.json().get("output", []):
        for part in item.get("content") or []:
            text += part.get("text", "")
            urls += [a.get("url", "") for a in part.get("annotations") or []]
    return text, urls


def ask_gemini(q: str) -> tuple[str, list[str]]:
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    r = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        json={"contents": [{"parts": [{"text": q}]}], "tools": [{"google_search": {}}]},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    cand = (r.json().get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
    chunks = (cand.get("groundingMetadata") or {}).get("groundingChunks") or []
    # Gemini cites through redirect URLs; the page title usually carries the domain.
    urls = [(c.get("web") or {}).get("uri", "") for c in chunks]
    urls += [(c.get("web") or {}).get("title", "") for c in chunks]
    return text, urls


PROVIDERS: dict[str, tuple[str, Callable[[str], tuple[str, list[str]]]]] = {
    "perplexity": ("PERPLEXITY_API_KEY", ask_perplexity),
    "openai": ("OPENAI_API_KEY", ask_openai),
    "gemini": ("GEMINI_API_KEY", ask_gemini),
}


def default_prompts(limit: int = 12) -> list[str]:
    """'Best X in Y' for the biggest city/category hubs, plus 'is X good?' for the
    most-reviewed businesses."""
    from app.seo import site
    from app.seo.model import build_hubs

    listings = site.load_listings()
    hubs = [h for h in build_hubs(listings).values() if h.level == "category"]
    hubs.sort(key=lambda h: -len(h.listings))
    out = [f"What are the best {h.what} in {h.city}, {h.place.split(', ')[-1]}?" for h in hubs]
    top = sorted(listings, key=lambda li: -li.business.review_count)
    out += [
        f"Is {li.business.name} in {li.business.city or li.business.country} any good? "
        "What do customers say?"
        for li in top
    ]
    return out[:limit]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--prompts", help="file with one question per line")
    ap.add_argument("--out", help="append JSON lines to this file")
    ap.add_argument("--limit", type=int, default=12)
    args = ap.parse_args()

    active = {n: fn for n, (key, fn) in PROVIDERS.items() if os.environ.get(key)}
    if not active:
        print("no provider key set (PERPLEXITY_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY)")
        return 2
    if args.prompts:
        prompts = [ln.strip() for ln in Path(args.prompts).read_text().splitlines() if ln.strip()]
    else:
        prompts = default_prompts(args.limit)

    run_at = datetime.now(UTC).isoformat(timespec="seconds")
    totals = {n: [0, 0] for n in active}
    sink = open(args.out, "a", encoding="utf-8") if args.out else None  # noqa: SIM115
    try:
        for q in prompts:
            for name, fn in active.items():
                row: dict = {"run_at": run_at, "provider": name, "question": q}
                try:
                    text, urls = fn(q)
                    row |= cited(text, urls)
                except Exception as e:  # noqa: BLE001
                    row["error"] = repr(e)[:300]
                totals[name][1] += 1
                totals[name][0] += int(bool(row.get("cited") or row.get("mentioned")))
                print(json.dumps(row, ensure_ascii=False))
                if sink:
                    sink.write(json.dumps(row, ensure_ascii=False) + "\n")
    finally:
        if sink:
            sink.close()
    for name, (hit, n) in totals.items():
        print(f"{name}: Afefehub cited or named in {hit}/{n} answers", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
