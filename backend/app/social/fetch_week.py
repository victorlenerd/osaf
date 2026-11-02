"""The week's published reviews, straight from DynamoDB.

There is no cross-business time index, so: businesses whose `updated_at` moved in the window
(GSI1 per category) -> each one's reviews in the window (SK range). Read-only.
"""

from __future__ import annotations

import logging

from app.models import Review
from app.social.candidates import Window, in_window
from app.store import dynamo

log = logging.getLogger(__name__)


def fetch_week_reviews(window: Window, *, scan: bool = False) -> list[Review]:
    if scan:
        reviews = dynamo.scan_reviews_between(window.since, window.until)
    else:
        businesses = dynamo.list_businesses_updated_since(window.since)
        log.info("%d businesses updated since %s", len(businesses), window.since)
        reviews = []
        for b in businesses:
            reviews.extend(dynamo.list_reviews_between(b.business_id, window.since, window.until))
    reviews = [r for r in reviews if in_window(r.created_at, window)]
    reviews.sort(key=lambda r: r.created_at, reverse=True)
    return reviews
