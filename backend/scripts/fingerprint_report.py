"""Pairwise similarity across every indexed review, to tune the duplicate thresholds.

    python scripts/fingerprint_report.py               # pairs scoring >= 0.3 on any kind
    python scripts/fingerprint_report.py --min 0.5 --limit 50

Prints the closest pairs with their exact/audio/video/text scores, and where each falls
against the current settings (DUPLICATE, similar, or below both). Read-only.
"""

from __future__ import annotations

import argparse
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.fingerprint import check  # noqa: E402
from app.models import Fingerprint  # noqa: E402
from app.store import opensearch  # noqa: E402


def _docs() -> list[dict]:
    body = {
        "size": 10_000,
        "query": {"match_all": {}},
        "_source": ["review_id", "business_id", "fp"],
    }
    hits = opensearch.client().search(index=get_settings().fingerprint_index, body=body)
    return [h["_source"] for h in hits["hits"]["hits"]]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min", type=float, default=0.3)
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()
    docs = _docs()
    fps = {d["review_id"]: (Fingerprint(**d.get("fp", {})), d.get("business_id")) for d in docs}
    rows = []
    for (a, (fa, _)), (b, (fb, bb)) in combinations(fps.items(), 2):
        m = check.score(fa, fb, b, bb)
        if m.exact or max(m.audio, m.video, m.text) >= args.min:
            rows.append((a, m))
    rows.sort(key=lambda r: (r[1].exact, max(r[1].audio, r[1].video, r[1].text)), reverse=True)
    s = get_settings()
    print(
        f"{len(fps)} reviews indexed; thresholds: duplicate audio>={s.dup_audio_threshold} "
        f"video>={s.dup_video_threshold}; similar audio>={s.similar_audio_threshold} "
        f"video>={s.similar_video_threshold} text>={s.similar_text_threshold}"
    )
    for a, m in rows[: args.limit]:
        verdict = "DUPLICATE" if check.is_duplicate(m) else "similar" if check.is_similar(m) else ""
        print(
            f"{a}  {m.review_id}  exact={int(m.exact)} audio={m.audio:.2f} "
            f"video={m.video:.2f} text={m.text:.2f}  {verdict}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
