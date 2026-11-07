"""Render every crawlable page (business pages, hubs, sitemaps, llms.txt, llms-full.txt) and
prune pages that no longer match a business. Also the self-healing nightly job.

    python scripts/render_site.py                    # to SITE_BUCKET, invalidate CloudFront
    python scripts/render_site.py --out /tmp/site    # to a local folder, from DynamoDB
    python scripts/render_site.py --fixture --out /tmp/site
                                                     # local preview from demo_seed.json,
                                                     # no AWS needed (demo rows included)
    python scripts/render_site.py --slugs-only       # backfill SLUG# pointers, no rendering

The first prod run after deploying this feature also backfills the SLUG# lookup pointers for
businesses published before slugs existed (idempotent).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import Business, BusinessSummary  # noqa: E402
from app.seo import site  # noqa: E402
from app.social.fixture import demo_reviews, load_entries  # noqa: E402
from app.store import dynamo  # noqa: E402

FIXTURE = Path(__file__).with_name("demo_seed.json")


class FixtureStore:
    """demo_seed.json as an in-memory store with the read API the site publisher uses."""

    def __init__(self, path: Path):
        self.businesses: dict[str, Business] = {}
        self.reviews: dict = {}
        self.summaries: dict[str, BusinessSummary] = {}
        for entry in load_entries(path):
            reviews = demo_reviews(entry)
            place = entry["business"]
            counts = {"yes": 0, "no": 0, "maybe": 0}
            for r in reviews:
                counts[r.extraction.recommend] += 1
            ratings = [r.extraction.rating for r in reviews if r.extraction.rating]
            b = Business(
                business_id=place["place_id"],
                source=place.get("source", "user"),
                name=place["name"],
                formatted_address=place["formatted_address"],
                country=place["country"],
                city=place.get("city"),
                lat=place.get("lat"),
                lng=place.get("lng"),
                category=reviews[0].extraction.category if reviews else "other",
                review_count=len(reviews),
                recommend_counts=counts,
                rating_sum=sum(ratings),
                rating_count=len(ratings),
                updated_at=max((r.created_at for r in reviews), default=""),
            )
            self.businesses[b.business_id] = b
            self.reviews[b.business_id] = reviews
            self.summaries[b.business_id] = BusinessSummary(
                **entry["summary"], review_count=len(reviews), model_version="demo-seed"
            )

    def get_business(self, bid):
        return self.businesses.get(bid)

    def list_reviews(self, bid, limit=100):
        return list(self.reviews.get(bid, []))

    def get_summary(self, bid):
        return self.summaries.get(bid)

    def list_all_businesses(self):
        return list(self.businesses.values())


def backfill_slugs() -> int:
    n = 0
    for b in dynamo.list_all_businesses():
        dynamo.put_slug_pointer(b)
        n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", help="write to this folder instead of the site bucket")
    ap.add_argument("--fixture", action="store_true", help="render demo_seed.json (needs --out)")
    ap.add_argument("--slugs-only", action="store_true", help="only backfill SLUG# pointers")
    args = ap.parse_args()

    if args.fixture:
        if not args.out:
            ap.error("--fixture needs --out")
        site.dynamo = FixtureStore(FIXTURE)  # type: ignore[assignment]
        site.ALLOW_DEMO = True
    else:
        print(f"slug pointers written: {backfill_slugs()}")
        if args.slugs_only:
            return 0

    writer = site.DirSiteWriter(args.out) if args.out else None
    result = site.render_all(writer)
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
