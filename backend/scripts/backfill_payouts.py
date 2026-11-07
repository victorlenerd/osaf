"""One-off before payouts launch: give existing published reviews what new ones get at
publish time, and report the legacy points balances.

    python scripts/backfill_payouts.py            # dry run: what would change
    python scripts/backfill_payouts.py --apply

For each published review whose submission media still exists under submissions/ (S3
expires that prefix after 30 days):
  - copy the media, transcript and face-check result to reviews/<id>/ and point the review
    at the copies, so they outlive the 30-day expiry;
  - compute its fingerprint (exact hash, audio, video, transcript), store it, index it and
    take the exact-media lock, so later copies of it are refused.
Reviews whose media has already expired are listed; they can still be matched on nothing.

For each reel published before we recorded who posted it, it reads the poster's Instagram
handle (yt-dlp metadata, no download), so the site credits the reel to that account rather
than to the person who sent the link.

Then it lists every legacy CONV#<phone>/POINTS balance (needs dynamodb:Scan, so run it with
a developer profile): the old Terms promised a gift card at 100 points, so anyone at 100 or
more must be honoured under the old rules before they are retired.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.fingerprint import index as fpindex  # noqa: E402
from app.fingerprint import media as fpmedia  # noqa: E402
from app.fingerprint import text as fptext  # noqa: E402
from app.models import CATEGORIES, Fingerprint, Review  # noqa: E402
from app.pipeline.download import DownloadError, extract_audio, reel_metadata  # noqa: E402
from app.store import dynamo, s3  # noqa: E402
from app.store import rewards_store as rstore  # noqa: E402


def _all_reviews() -> list[Review]:
    out: list[Review] = []
    seen: set[str] = set()
    for cat in CATEGORIES:
        for b in dynamo.list_businesses_by_category(cat, limit=10_000):
            if b.business_id in seen:
                continue
            seen.add(b.business_id)
            out.extend(dynamo.list_reviews(b.business_id, limit=1000))
    return out


def _fingerprint(review: Review, work: Path) -> Fingerprint | None:
    sid = review.submission_id
    if review.source == "reel":
        source = work / "source.mp4"
        try:
            s3.download_file(s3.Keys.video(sid), source)
        except Exception:  # noqa: BLE001
            return None
        audio = extract_audio(source, work / "audio.wav")
        video = fpmedia.video_fingerprint(source)
    else:
        source = work / "voice.ogg"
        try:
            s3.download_file(s3.Keys.voice_source(sid), source)
        except Exception:  # noqa: BLE001
            return None
        audio = extract_audio(source, work / "audio.wav")
        video = []
    fp = Fingerprint(
        sha256=fpmedia.sha256_file(source), audio=fpmedia.audio_fingerprint(audio), video=video
    )
    try:
        raw = s3.get_json(s3.Keys.transcript_json(sid))
        fp.text = fptext.minhash(str(raw.get("transcript") or ""))
    except Exception:  # noqa: BLE001
        pass
    return fp


def backfill(apply: bool) -> None:
    reviews = [r for r in _all_reviews() if r.status == "published"]
    todo = expired = dupes = 0
    for r in reviews:
        if r.fingerprint_s3_key:
            continue
        work = Path(tempfile.mkdtemp(prefix="afefehub-backfill-"))
        try:
            fp = _fingerprint(r, work)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        if fp is None:
            expired += 1
            print(f"  media expired  {r.review_id} ({r.created_at[:10]})")
            continue
        print(
            f"  fingerprint    {r.review_id} audio={len(fp.audio)} video={len(fp.video)} "
            f"text={'yes' if fp.text else 'no'}"
        )
        todo += 1
        if not apply:
            continue
        sid = r.submission_id
        key = s3.Keys.review_copy(r.review_id, s3.Keys.fingerprint(sid))
        s3.put_json(fp.model_dump(), key)
        r.fingerprint_s3_key = key
        r.media_sha256 = fp.sha256
        for attr in ("video_s3_key", "audio_s3_key", "transcript_s3_key"):
            old = getattr(r, attr)
            if old and old.startswith("submissions/"):
                try:
                    setattr(r, attr, s3.copy(old, s3.Keys.review_copy(r.review_id, old)))
                except Exception as e:  # noqa: BLE001
                    print(f"    could not copy {old}: {e!r}", file=sys.stderr)
        dynamo.put_review(r)
        fpindex.put(r.review_id, r.business_id, r.reviewer_phone_hash, r.created_at, fp)
        if fp.sha256 and not rstore.claim_media(fp.sha256, r.review_id):
            dupes += 1
            print(f"    exact duplicate of an earlier review: {r.review_id}")
    verb = "backfilled" if apply else "would backfill"
    print(f"{verb} {todo} reviews; {expired} with expired media; {dupes} exact duplicates")


def backfill_posters(apply: bool) -> None:
    reels = [r for r in _all_reviews() if r.source == "reel" and r.reel_url and not r.ig_username]
    found = 0
    for r in reels:
        work = Path(tempfile.mkdtemp(prefix="afefehub-meta-"))
        try:
            meta = reel_metadata(r.reel_url or "", work)
        except DownloadError as e:
            print(f"  poster unknown {r.review_id}: {str(e)[:80]}")
            continue
        finally:
            shutil.rmtree(work, ignore_errors=True)
        if not meta.username:
            print(f"  poster unknown {r.review_id}")
            continue
        found += 1
        print(f"  poster         {r.review_id} @{meta.username}")
        if apply:
            r.ig_username, r.ig_uploader_id = meta.username, meta.uploader_id
            r.ig_posted_at = meta.posted_at
            r.ig_author_verified = rstore.get_ig_link(meta.username) == r.reviewer_phone_hash
            dynamo.put_review(r)
    verb = "recorded" if apply else "would record"
    print(f"{verb} the poster of {found} of {len(reels)} older reels")


def legacy_points() -> None:
    table = dynamo._table()
    kwargs: dict = {"FilterExpression": "SK = :s", "ExpressionAttributeValues": {":s": "POINTS"}}
    rows = []
    while True:
        r = table.scan(**kwargs)
        rows.extend(r.get("Items", []))
        if "LastEvaluatedKey" not in r:
            break
        kwargs["ExclusiveStartKey"] = r["LastEvaluatedKey"]
    owed = [i for i in rows if int(i.get("points", 0)) >= 100]
    print(f"legacy points balances: {len(rows)}; at 100 or more: {len(owed)}")
    for i in owed:
        print(f"  {i['PK'][5:]}  {int(i['points'])} points")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--skip-points", action="store_true", help="skip the legacy points scan")
    args = ap.parse_args()
    fpindex.ensure_index()
    backfill(args.apply)
    backfill_posters(args.apply)
    if not args.skip_points:
        legacy_points()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
