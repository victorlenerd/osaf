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
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import BusinessSummary, PlaceRef, Review, ReviewExtraction, Visit  # noqa: E402
from app.store import dynamo, opensearch  # noqa: E402

FIXTURE = Path(__file__).with_name("demo_seed.json")
DEMO_PREFIX = "afefe:demo-"


def _load() -> list[dict]:
    data = json.loads(FIXTURE.read_text())
    for entry in data["businesses"]:
        assert entry["business"]["place_id"].startswith(DEMO_PREFIX), entry["business"]["place_id"]
    return data["businesses"]


def purge(entries: list[dict]) -> None:
    for entry in entries:
        bid = entry["business"]["place_id"]
        n = dynamo.delete_business(bid)
        opensearch.delete_business(bid)
        print(f"purged {bid}: {n} dynamo items")


def seed(entries: list[dict]) -> None:
    for entry in entries:
        place = PlaceRef(**entry["business"])
        reviews: list[Review] = []
        for i, r in enumerate(sorted(entry["reviews"], key=lambda x: x["created_at"])):
            ext = ReviewExtraction(
                business=place,
                business_name_as_said=r["business_name_as_said"],
                visit=Visit(**r.get("visit", {})),
                good=r["good"],
                improve=r["improve"],
                recommend=r["recommend"],
                category=r["category"],
                keywords=r["keywords"],
                overall_sentiment=r["overall_sentiment"],
                language=r.get("language", "en"),
                confidence={"business": 1.0},
                one_line_summary=r["one_line_summary"],
            )
            review = Review(
                review_id=f"demo-{r['reel_shortcode'].lower()}",
                business_id=place.place_id,
                submission_id=f"demo-sub-{r['reel_shortcode'].lower()}",
                reviewer_phone_hash=f"demo-reviewer-{i}",
                reviewer_display_name=r.get("reviewer_display_name"),
                reel_url=f"https://www.instagram.com/reel/{r['reel_shortcode']}/",
                reel_shortcode=r["reel_shortcode"],
                extraction=ext,
                created_at=r["created_at"],
            )
            dynamo.put_review(review)
            business = dynamo.upsert_business_on_publish(ext)
            reviews.append(review)

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
    entries = _load()
    purge(entries)
    if not args.purge:
        seed(entries)
