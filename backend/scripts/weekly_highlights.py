"""Weekly "Reviews of the week" on Instagram: pick, render, caption. Dry run by default.

Two kinds of post per week: the round-up carousel (cover, one slide per review, closing CTA),
and then a Reel of its own for each review in it, playing that reviewer's whole recording (the
voice note, or the reel's soundtrack) under the review card with a waveform that fills in as it
plays. --no-reels makes the carousel only.

Real data (read-only DynamoDB queries; needs AWS credentials, e.g. AWS_PROFILE=prod) and Muse
Spark ranking (MODEL_API_KEY in the repo-root .env; run from the repo root):

    PYTHONPATH=backend AWS_PROFILE=prod backend/.venv/bin/python \\
        backend/scripts/weekly_highlights.py                  # last 7 days, model-ranked
    ... --exclude <id>,<id>                                   # drop picks you dislike, rerun
    ... --from-picks .local/weekly/<window>/picks.json        # re-render exactly those picks
    ... --no-model                                            # heuristic order, no model call
    ... --pick <id>,<id>                                      # hand-picked, in slide order

The Reels read each pick's audio from S3 (read-only). --audio-dir DIR uses local files named
<review_id>.<m4a|mp4|ogg|wav|...> instead; the demo fixture has no audio, so it needs one
(or --no-reels):

    .venv/bin/python scripts/weekly_highlights.py --from-fixture scripts/demo_seed.json \\
        --since 2026-10-18 --until 2026-10-27 --audio-dir <dir>

Outputs slide-NN.jpg, preview.png (contact sheet), caption.txt and picks.json in --out (default
.local/weekly/<since>_<until> at the repo root), plus reels/<review_id>/ with reel.mp4,
reel-cover.jpg, reel-preview.png and caption.txt per review. Nothing leaves the machine unless:

    ... --preflight        # read-only: which IG account the token posts as, and today's quota
    ... --publish [--yes]  # upload to S3, publish the carousel then each Reel (Graph API)
                           # (asks for a typed "yes" first; --yes skips that for automation)

--publish needs IG_USER_ID and IG_ACCESS_TOKEN (root .env locally, SSM in prod). Each post is
recorded in published.json (next to the output and in s3://<media bucket>/social/weekly/<window>/)
as soon as it is live; a rerun skips whatever either copy records.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.models import Review  # noqa: E402
from app.social.candidates import Candidate, select_candidates, window_from_dates  # noqa: E402
from app.social.caption import (  # noqa: E402
    assert_caption_ok,
    build_caption,
    build_review_caption,
)
from app.social.flags import flag_emoji  # noqa: E402
from app.social.instagram import InstagramPublishError, client_from_settings  # noqa: E402
from app.social.rank import Pick, Picks, RankResult, rank, read_picks, write_picks  # noqa: E402
from app.social.render import render_carousel  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def _csv(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _load_reviews(args) -> tuple[list[Review], str]:
    if args.from_fixture:
        from app.social.fixture import load_demo_reviews

        return load_demo_reviews(args.from_fixture), f"fixture:{args.from_fixture}"
    from app.social.fetch_week import fetch_week_reviews

    return fetch_week_reviews(args.window, scan=args.scan), "dynamodb" + (
        ":scan" if args.scan else ""
    )


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    src = ap.add_argument_group("source")
    src.add_argument("--from-fixture", type=Path, help="demo_seed.json instead of DynamoDB")
    src.add_argument("--from-picks", type=Path, help="an earlier picks.json: skip fetch and model")
    src.add_argument("--scan", action="store_true", help="DynamoDB Scan instead of index queries")
    src.add_argument("--include-demo", action="store_true", help="allow afefe:demo-* reviews")
    win = ap.add_argument_group("window")
    win.add_argument("--since", help="YYYY-MM-DD inclusive (default: 7 days before --until / now)")
    win.add_argument("--until", help="YYYY-MM-DD exclusive (default: --since + 7 days / now)")
    sel = ap.add_argument_group("selection")
    sel.add_argument("--pick", help="comma-separated review ids, in slide order (no model)")
    sel.add_argument("--exclude", help="comma-separated review ids to leave out")
    sel.add_argument("--max", type=int, default=5, help="max review slides (default 5)")
    sel.add_argument("--min", type=int, default=3, help="warn below this many (default 3)")
    sel.add_argument("--no-model", action="store_true", help="heuristic order, no Muse Spark")
    out = ap.add_argument_group("output")
    out.add_argument("--no-reels", action="store_true", help="the carousel only, no Reels")
    out.add_argument("--audio-dir", type=Path, help="Reels: local <review_id>.<ext> audio files")
    out.add_argument(
        "--max-seconds",
        type=float,
        default=870.0,
        help="Reels: cut a recording longer than this (default 870, under IG's 15 min)",
    )
    out.add_argument("--no-flags", action="store_true", help="offline: ISO chips, no Twemoji")
    out.add_argument("--hook", help="first line of the caption (overrides the model's)")
    out.add_argument("--wa-number", help="public WhatsApp number as displayed (default: settings)")
    out.add_argument("--site-url", help="site shown on slides (default: settings, no scheme)")
    out.add_argument("--out", type=Path, help="output dir (default .local/weekly/<since>_<until>)")
    pub = ap.add_argument_group("publishing")
    pub.add_argument(
        "--preflight", action="store_true", help="check the IG token and quota, then exit"
    )
    pub.add_argument("--publish", action="store_true", help="upload to S3 and publish the week")
    pub.add_argument("--yes", action="store_true", help="skip the typed confirmation (automation)")
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = _parser()
    args = ap.parse_args(argv)
    settings = get_settings()
    if args.preflight:
        return preflight(settings)
    if args.publish:
        try:
            client_from_settings(settings)  # fail closed before any work is done
        except InstagramPublishError as e:
            print(f"--publish: {e}", file=sys.stderr)
            return 2
    wa_number = args.wa_number if args.wa_number is not None else settings.whatsapp_public_number
    site_url = args.site_url or settings.public_site_url.split("://", 1)[-1].rstrip("/")
    exclude = set(_csv(args.exclude))
    pick_ids = _csv(args.pick)

    # ---- candidates: an earlier picks.json, or reviews from the fixture / DynamoDB
    skipped: list[tuple[str, str]] = []
    if args.from_picks:
        prior = read_picks(args.from_picks)
        args.window = (
            window_from_dates(args.since, args.until)
            if (args.since or args.until)
            else window_from_dates(prior.window["since"][:10], prior.window["until"][:10])
        )
        pool = [c for c in prior.candidates if c.review_id not in exclude]
        skipped = [(c.review_id, "excluded") for c in prior.candidates if c.review_id in exclude]
        source = f"picks:{args.from_picks}"
        result = RankResult(
            picks=pool
            if not pick_ids
            else [c for rid in pick_ids for c in pool if c.review_id == rid],
            reasons={p.review_id: p.reason for p in prior.picks},
            hook=prior.hook,
            model=prior.model,
        )
        considered = len(prior.candidates)
    else:
        args.window = window_from_dates(args.since, args.until)
        reviews, source = _load_reviews(args)
        include_demo = args.include_demo or bool(args.from_fixture)
        if pick_ids:
            picks, skipped = select_candidates(
                reviews, args.window, pick=pick_ids, exclude=exclude, include_demo=include_demo
            )
            result = RankResult(picks=picks, model="manual")
            considered = len(picks)
        else:
            pool, skipped = select_candidates(
                reviews,
                args.window,
                exclude=exclude,
                include_demo=include_demo,
                max_picks=None,
                one_per_business=False,
            )
            considered = len(pool)
            use_model = not args.no_model
            if use_model and not settings.model_api_key:
                print("MODEL_API_KEY is not set; using the heuristic order", file=sys.stderr)
                use_model = False
            result = rank(pool, max_picks=args.max, min_picks=args.min, use_model=use_model)
        print(f"source  {source}: {len(reviews)} reviews")

    window = args.window
    out = args.out or REPO / ".local" / "weekly" / f"{window.since[:10]}_{window.until[:10]}"
    out.mkdir(parents=True, exist_ok=True)
    print(f"window  {window.since} -> {window.until}")
    print(f"picks   {considered} candidates, ranked by {result.model}")
    for rid, reason in skipped:
        print(f"  skip  {rid:<28} {reason}")
    picks: list[Candidate] = result.picks
    if not picks:
        print("no eligible reviews in this window; nothing rendered", file=sys.stderr)
        return 2
    if len(picks) < args.min:
        print(
            f"note: only {len(picks)} review slide(s); {args.min} to {args.max} reads best",
            file=sys.stderr,
        )

    print(f"\n{'#':<3}{'review_id':<28}{'business':<26}{'city':<11}{'flag':<6}{'rec':<7}reason")
    for i, c in enumerate(picks, start=2):
        flag = flag_emoji(c.reviewer_country) or (c.reviewer_country or "--")
        biz, city = c.business_name[:24], (c.city or "")[:9]
        reason = result.reasons.get(c.review_id, "")
        print(f"{i:<3}{c.review_id:<28}{biz:<26}{city:<11}{flag:<6}{c.recommend:<7}{reason}")
    if result.hook:
        print(f"\nhook    {result.hook}")

    hook = args.hook or result.hook or None
    caption = build_caption(picks, window, hook=hook, wa_number=wa_number, site_url=site_url)
    assert_caption_ok(caption)
    (out / "caption.txt").write_text(caption + "\n")
    write_picks(
        Picks(
            window=window.as_dict(),
            model=result.model,
            source=source,
            hook=hook or "",
            picks=[
                Pick(review_id=c.review_id, reason=result.reasons.get(c.review_id, ""))
                for c in picks
            ],
            excluded=sorted(exclude),
            candidates_considered=considered,
            candidates=picks,
        ),
        out / "picks.json",
    )
    paths = render_carousel(
        picks, window, out, wa_number=wa_number, site_url=site_url, flag_fetch=not args.no_flags
    )
    print(f"\n{len(paths)} slides -> {out}")
    for p in paths:
        print(f"  {p.name}  {p.stat().st_size // 1024} KB")
    print(f"  preview.png  caption.txt ({len(caption)} chars)  picks.json")

    reels = [] if args.no_reels else render_reels(picks, args, window, out, wa_number, site_url)
    if not args.publish:
        print("\nnot happy with a pick? rerun with --exclude <id>; happy? add --publish")
        return 0
    run_id = f"{window.since[:10]}_{window.until[:10]}"
    return publish(settings, paths, caption, reels, out, run_id=run_id, assume_yes=args.yes)


def render_reels(
    picks: list[Candidate], args, window, out: Path, wa_number: str, site_url: str
) -> list:
    """One Reel per pick with that review's whole recording, from --audio-dir or S3, into
    out/reels/<review_id>/. A pick with no audio keeps its slide and just gets no Reel."""
    from app.social import audio as au
    from app.social.reel import render_review_reel
    from app.social.weekly_publish import ReelJob

    jobs: list[ReelJob] = []
    print(f"\nreels   one per review, whole recording (cut past {args.max_seconds:.0f} s)")
    with tempfile.TemporaryDirectory(dir=out) as tmp:
        for c in picks:
            if args.audio_dir:
                sources = au.local_sources(c, args.audio_dir)
            elif args.from_fixture:
                sources = iter(())
            else:
                sources = au.s3_sources(c, Path(tmp))
            try:
                src, clip = au.first_clip(c.review_id, sources, max_s=args.max_seconds)
            except au.ReviewAudioError as e:
                print(f"  skip  {c.review_id:<28} {e}: slide only", file=sys.stderr)
                continue
            dest = out / "reels" / c.review_id
            res = render_review_reel(
                c, clip, window, dest, wa_number=wa_number, site_url=site_url,
                flag_fetch=not args.no_flags, flag_cache=out / ".flags",
            )  # fmt: skip
            cap = build_review_caption(c, window, wa_number=wa_number, site_url=site_url)
            assert_caption_ok(cap)
            (dest / "caption.txt").write_text(cap + "\n")
            cut = " (cut)" if clip.end_ms < src.duration_ms else ""
            size_mb = res.video.stat().st_size / 1_000_000
            print(
                f"  reel  {c.review_id:<28} {c.business_name[:24]:<26}"
                f"{res.duration_s:6.1f} s{cut}  {size_mb:.1f} MB"
            )
            jobs.append(
                ReelJob(c.review_id, c.business_name, res.video, res.cover, cap, res.duration_s)
            )
    if jobs:
        print(f"  -> {out / 'reels'}")
    return jobs


def preflight(settings) -> int:
    """Read-only: who the token posts as and how much of the 24 h quota is used."""
    try:
        client = client_from_settings(settings)
        me = client.me()
        quota = client.publishing_limit()
    except InstagramPublishError as e:
        print(f"preflight failed: {e}", file=sys.stderr)
        return 2
    used = quota.get("quota_usage", "?")
    total = (quota.get("config") or {}).get("quota_total", "?")
    print(f"account  @{me.get('username', '?')} ({me.get('name', '')}, id {me.get('id', '?')})")
    print(f"quota    {used}/{total} posts used in the last 24 h")
    print(f"api      {client.base}")
    return 0


def publish(
    settings,
    slides: list[Path],
    caption: str,
    reels: list,
    out: Path,
    *,
    run_id: str,
    assume_yes: bool,
) -> int:
    """Publish the carousel, then each Reel; record each one as it lands."""
    from app.social.weekly_publish import merge_records, new_record, pending, publish_week
    from app.store import s3

    rec_path = out / "published.json"
    local = json.loads(rec_path.read_text()) if rec_path.exists() else None
    try:  # the S3 copy is the durable one: a rerun from another machine must see it too
        remote = s3.get_json_or_none(s3.Keys.social_record(run_id))
    except Exception as e:  # noqa: BLE001
        print(f"publish aborted: cannot read the S3 publish record: {e}", file=sys.stderr)
        return 2
    try:
        client = client_from_settings(settings)
        me = client.me()
        quota = client.publishing_limit()
    except InstagramPublishError as e:
        print(f"publish aborted: {e}", file=sys.stderr)
        return 2
    record = merge_records(
        new_record(run_id, me.get("username", ""), local),
        new_record(run_id, me.get("username", ""), remote),
    )
    do_carousel, todo = pending(record, reels)
    if not do_carousel and not todo:
        print(f"\neverything for {run_id} is already published (see {rec_path})")
        return 0

    used = quota.get("quota_usage", "?")
    total = (quota.get("config") or {}).get("quota_total", "?")
    n_posts = int(do_carousel) + len(todo)
    if isinstance(used, int) and isinstance(total, int) and total - used < n_posts:
        print(
            f"publish aborted: {n_posts} posts but only {total - used} left today", file=sys.stderr
        )
        return 2
    print(
        f"\nabout to publish {n_posts} post(s) to @{me.get('username', '?')} (quota {used}/{total})"
    )
    if do_carousel:
        print(f"  carousel  {len(slides)} slides")
        print("\n".join("    | " + line for line in caption.splitlines()))
    else:
        print("  carousel  already published, skipped")
    for j in todo:
        first = j.caption.splitlines()[0]
        print(f"  reel      {j.business[:28]:<30}{j.duration_s:6.1f} s  | {first}")
    if not assume_yes:
        if not sys.stdin.isatty():
            print(
                "no terminal to confirm on; pass --yes to publish non-interactively",
                file=sys.stderr,
            )
            return 2
        if input("type yes to publish: ").strip().lower() != "yes":
            print("not published")
            return 1

    def upload(path: Path, key: str, content_type: str) -> str:
        s3.upload_file(path, key, content_type=content_type)
        return s3.presigned_url(key, expires=3 * 3600)

    def save(rec: dict) -> None:
        rec_path.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
        try:
            s3.put_json(rec, s3.Keys.social_record(run_id))
        except Exception as e:  # noqa: BLE001  (the post is live; the S3 copy is bookkeeping)
            print(f"warning: could not write the S3 publish record: {e}", file=sys.stderr)

    ok = publish_week(
        client, record, run_id=run_id, slides=slides, caption=caption, reels=todo,
        upload=upload, save=save,
    )  # fmt: skip
    print(f"\nrecord: {rec_path}")
    if car := record.get("carousel"):
        print(f"  carousel  {car.get('permalink') or car.get('media_id')}")
    for r in record["reels"]:
        print(f"  reel      {r['business'][:28]:<30}{r.get('permalink') or r['media_id']}")
    if not ok:
        print("some posts failed; rerun the same command to finish the rest", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
