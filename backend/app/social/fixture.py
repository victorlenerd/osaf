"""Build Review objects from scripts/demo_seed.json.

Shared by the demo seeder (writes them to DynamoDB) and the weekly highlights CLI
(``--from-fixture``: render a sample carousel with no AWS access).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.models import PlaceRef, Review, ReviewExtraction, Visit

DEMO_PREFIX = "afefe:demo-"


def load_entries(path: Path) -> list[dict]:
    data = json.loads(Path(path).read_text())
    for entry in data["businesses"]:
        pid = entry["business"]["place_id"]
        assert pid.startswith(DEMO_PREFIX), pid
    return data["businesses"]


def demo_reviews(entry: dict) -> list[Review]:
    """One fixture business -> its reviews, oldest first, with deterministic demo ids."""
    place = PlaceRef(**entry["business"])
    out: list[Review] = []
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
        code = r["reel_shortcode"]
        out.append(
            Review(
                review_id=f"demo-{code.lower()}",
                business_id=place.place_id,
                submission_id=f"demo-sub-{code.lower()}",
                reviewer_phone_hash=f"demo-reviewer-{i}",
                reviewer_display_name=r.get("reviewer_display_name"),
                reviewer_country=r.get("reviewer_country"),
                reel_url=f"https://www.instagram.com/reel/{code}/",
                reel_shortcode=code,
                extraction=ext,
                created_at=r["created_at"],
            )
        )
    return out


def load_demo_reviews(path: Path) -> list[Review]:
    return [r for entry in load_entries(path) for r in demo_reviews(entry)]
