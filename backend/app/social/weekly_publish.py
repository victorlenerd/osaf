"""Publish one week: the round-up carousel first, then each picked review's own Reel.

Each success is written to the run's record (published.json) the moment it lands, and anything
the record already lists is skipped, so rerunning after a partial failure finishes the week
without posting anything twice. A failed carousel stops the run (the Reels point back to it);
a failed Reel is reported and the next one still goes. Nothing is retried automatically.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.models import now_iso
from app.social.instagram import (
    InstagramClient,
    InstagramPublishError,
    publish_carousel,
    publish_reel,
)
from app.store.s3 import Keys

# (local file, S3 key, content type) -> a URL Instagram can fetch
Upload = Callable[[Path, str, str], str]


@dataclass
class ReelJob:
    review_id: str
    business: str
    video: Path
    cover: Path | None
    caption: str
    duration_s: float


def new_record(run_id: str, account: str, previous: dict | None = None) -> dict:
    """The run's record, carrying over what an earlier run already published. A record from
    before single-review Reels (one post at the top level) is kept under ``earlier``."""
    rec = {"run_id": run_id, "account": account, "carousel": None, "reels": [], "earlier": []}
    if not previous:
        return rec
    if "carousel" in previous or "reels" in previous:
        rec.update({k: previous.get(k, rec[k]) for k in ("carousel", "reels", "earlier")})
        rec["earlier"] = list(rec["earlier"] or [])
        rec["reels"] = list(rec["reels"] or [])
    elif previous.get("media_id"):
        if previous.get("format", "carousel") == "carousel":
            rec["carousel"] = {
                k: previous.get(k) for k in ("media_id", "permalink", "published_at")
            }
        else:
            rec["earlier"] = [previous]
    return rec


def pending(record: dict, reels: list[ReelJob]) -> tuple[bool, list[ReelJob]]:
    done = {r.get("review_id") for r in record.get("reels") or []}
    return record.get("carousel") is None, [j for j in reels if j.review_id not in done]


def publish_week(
    client: InstagramClient,
    record: dict,
    *,
    run_id: str,
    slides: list[Path],
    caption: str,
    reels: list[ReelJob],
    upload: Upload,
    save: Callable[[dict], None],
    say: Callable[[str], None] = print,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    """Publish what ``record`` does not list yet. Returns True when nothing failed."""
    do_carousel, todo = pending(record, reels)
    ok = True
    if do_carousel:
        urls = [
            upload(p, Keys.social_slide(run_id, i), "image/jpeg")
            for i, p in enumerate(slides, start=1)
        ]
        say(f"uploaded {len(urls)} slides")
        try:
            media_id, link = publish_carousel(client, urls, caption, say=say, sleep=sleep)
        except InstagramPublishError as e:
            say(f"carousel failed: {e}; not posting the Reels either")
            return False
        record["carousel"] = {
            "media_id": media_id,
            "permalink": link,
            "published_at": now_iso(),
            "slides": [p.name for p in slides],
            "caption": caption,
        }
        save(record)
        say(f"carousel published: {link or media_id}")

    for job in todo:
        try:
            video_url = upload(
                job.video, Keys.social_review_reel(run_id, job.review_id), "video/mp4"
            )
            cover_url = (
                upload(
                    job.cover, Keys.social_review_reel_cover(run_id, job.review_id), "image/jpeg"
                )
                if job.cover
                else ""
            )
            media_id, link = publish_reel(
                client, video_url, job.caption, cover_url=cover_url, say=say, sleep=sleep
            )
        except Exception as e:  # noqa: BLE001  (one Reel failing must not stop the next)
            say(f"reel for {job.review_id} ({job.business}) failed: {e}")
            ok = False
            continue
        record["reels"].append(
            {
                "review_id": job.review_id,
                "business": job.business,
                "media_id": media_id,
                "permalink": link,
                "published_at": now_iso(),
                "duration_s": round(job.duration_s, 1),
                "caption": job.caption,
            }
        )
        save(record)
        say(f"reel for {job.business} published: {link or media_id}")
    return ok
