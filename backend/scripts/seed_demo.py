"""Seed (or purge) fictional demo businesses so the public site has content before real
reviews exist.

    python scripts/seed_demo.py            # purge any previous demo rows, then seed
    python scripts/seed_demo.py --purge    # remove demo rows only

Writes go through the same store helpers the publish path uses (DynamoDB upsert +
OpenSearch index), with the business summary written by hand instead of Muse Spark.
Every demo business id starts with ``afefe:demo-``; nothing else is touched.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import BusinessSummary, PlaceRef  # noqa: E402
from app.social.fixture import demo_reviews, load_entries  # noqa: E402
from app.store import dynamo, opensearch  # noqa: E402

FIXTURE = Path(__file__).with_name("demo_seed.json")


def purge(entries: list[dict]) -> None:
    for entry in entries:
        bid = entry["business"]["place_id"]
        n = dynamo.delete_business(bid)
        opensearch.delete_business(bid)
        print(f"purged {bid}: {n} dynamo items")


def seed(entries: list[dict]) -> None:
    for entry in entries:
        place = PlaceRef(**entry["business"])
        reviews = demo_reviews(entry)
        for review in reviews:
            dynamo.put_review(review)
            business = dynamo.upsert_business_on_publish(review.extraction)

        counts = {"yes": 0, "no": 0, "maybe": 0}
        for rv in reviews:
            counts[rv.extraction.recommend] += 1
        total = sum(counts.values())
        summary = BusinessSummary(
            **entry["summary"],
            recommendation_rate=round(counts["yes"] / total, 3) if total else 0.0,
            review_count=total,
            last_review_at=max(rv.created_at for rv in reviews),
            model_version="demo-seed",
        )
        dynamo.put_summary(place.place_id, summary)
        opensearch.upsert_business(business, summary)
        print(f"seeded {place.place_id}: {total} reviews, {business.name}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--purge", action="store_true", help="remove demo rows and exit")
    args = ap.parse_args()
    entries = load_entries(FIXTURE)
    purge(entries)
    if not args.purge:
        seed(entries)
