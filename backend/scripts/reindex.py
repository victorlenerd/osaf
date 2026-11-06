"""Rebuild the OpenSearch `businesses` index from DynamoDB, the source of truth.

    python scripts/reindex.py                      # every business, all categories
    python scripts/reindex.py <business_id> [...]  # just these

Use it after an OpenSearch outage: the publish path keeps the review and the business
in DynamoDB even when the index write fails (it is logged, not retried), so a business
can be live at /business/<id> yet missing from search and the category filters.
Each business is re-indexed exactly as a publish would index it, summary included.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import CATEGORIES, Business  # noqa: E402
from app.store import dynamo, opensearch  # noqa: E402


def all_businesses() -> list[Business]:
    # Reads the same category GSI the public API uses; the demo seed rows are included.
    return dynamo.list_businesses_updated_since("0000")


def reindex(businesses: list[Business]) -> int:
    for b in businesses:
        summary = dynamo.get_summary(b.business_id)
        opensearch.upsert_business(b, summary)
        print(f"indexed {b.business_id}: {b.name} [{b.category}] {b.review_count} reviews")
    return len(businesses)


def main(argv: list[str]) -> int:
    opensearch.ensure_index()
    if argv:
        found, missing = [], []
        for bid in argv:
            b = dynamo.get_business(bid)
            (found if b else missing).append(b or bid)
        n = reindex(found)
        for bid in missing:
            print(f"not in DynamoDB: {bid}", file=sys.stderr)
        print(f"reindexed {n} of {len(argv)}")
        return 1 if missing else 0
    n = reindex(all_businesses())
    print(f"reindexed {n} businesses across {len(CATEGORIES)} categories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
