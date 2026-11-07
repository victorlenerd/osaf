"""Monthly payout run (Nigeria). Three steps, each run by hand from a laptop:

    # 1. after the month ends: a spreadsheet of every entry in the window, one sheet per
    #    category group, with what you need to judge each review
    python scripts/payout.py export --window 2026-11

    # 2. fill the `decision` column (approve / void / ban; blank = approve) and `note`, then
    #    compute the pro-rata amounts and the transfer list (dry run unless --apply)
    python scripts/payout.py settle --window 2026-11 --sheet payout-2026-11.xlsx --apply

    # 3. make the bank transfers yourself, then record them and tell each payee on WhatsApp
    python scripts/payout.py mark-paid --window 2026-11 --csv transfers-2026-11.csv --apply

Reads DynamoDB through GSI1 (WINDOW#<yyyy-mm>), so no Scan permission is needed. Needs the
`ops` extra (openpyxl): pip install -e ".[ops]". Runs with the AWS credentials and .env the
backend uses. The spreadsheet and CSV hold bank details and phone numbers: keep them off
shared drives and delete them once the window is paid.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.fingerprint import check as fpcheck  # noqa: E402
from app.models import Fingerprint, PayoutEntry, Review, now_iso  # noqa: E402
from app.moderation import bans  # noqa: E402
from app.pipeline.download import DownloadError, reel_metadata  # noqa: E402
from app.pipeline.publish import business_url  # noqa: E402
from app.rewards import rules, settle  # noqa: E402
from app.store import dynamo, s3  # noqa: E402
from app.store import rewards_store as rstore  # noqa: E402
from app.whatsapp import client as wa  # noqa: E402

PRESIGN_SECONDS = 7 * 86400  # the longest a SigV4 presigned URL can live
COLUMNS = [
    "review_id", "reviewer", "phone", "reviewer_ref", "entries_in_window", "already_banned",
    "business", "category", "kind", "points", "author_verified", "ig_username", "review_page",
    "media_link", "summary", "transcript", "face_coverage", "ig_likes", "ig_comments",
    "ig_views", "closest_review", "match_audio", "match_video", "match_text", "flags",
    "status", "decision", "note",
]  # fmt: skip
TRANSFER_COLUMNS = [
    "phone_hash", "phone", "method", "bank_name", "account_number", "account_name",
    "amount_ngn", "window", "review_ids",
]  # fmt: skip


def _mask(phone: str | None) -> str:
    return f"***{phone[-4:]}" if phone else ""


def _transcript(review: Review) -> str:
    if not review.transcript_s3_key:
        return ""
    try:
        raw = s3.get_json(review.transcript_s3_key)
        return str(raw.get("transcript") or "")[:1500]
    except Exception:  # noqa: BLE001
        return ""


def _closest(review: Review):
    if not review.fingerprint_s3_key:
        return None
    try:
        fp = Fingerprint(**s3.get_json(review.fingerprint_s3_key))
    except Exception:  # noqa: BLE001
        return None
    return fpcheck.check(fp, exclude=review.review_id).best


def _row(e: PayoutEntry, review: Review | None, counts: dict[str, int], metrics: bool) -> dict:
    row = {c: "" for c in COLUMNS}
    row.update(
        review_id=e.review_id,
        phone=_mask(e.phone),
        reviewer_ref=e.phone_hash[:8],
        entries_in_window=counts.get(e.phone_hash, 0),
        already_banned="yes" if rstore.get_ban(e.phone_hash) else "",
        business=e.business_name,
        category=e.category,
        kind=e.kind,
        points=e.points,
        author_verified="yes" if e.kind == "reel_author" else "",
        ig_username=e.ig_username or "",
        status=e.status,
        note=e.note or "",
    )
    flags = []
    if e.kind == "reel_unverified":
        flags.append("author not verified yet: voided at settle unless verified first")
    if not e.similarity_checked:
        flags.append("duplicate check incomplete at publish")
    if review is None:
        flags.append("review deleted")
        row["flags"] = "; ".join(flags)
        return row
    if review.status != "published":
        flags.append("review hidden")
    row.update(
        reviewer=review.reviewer_display_name or "",
        review_page=business_url(review.business_id),
        summary=review.extraction.one_line_summary,
        transcript=_transcript(review),
        face_coverage=round(review.face_check.face_frame_coverage, 2) if review.face_check else "",
    )
    media = review.video_s3_key or review.audio_s3_key
    if media:
        try:
            row["media_link"] = s3.presigned_url(media, expires=PRESIGN_SECONDS)
        except Exception:  # noqa: BLE001
            flags.append("media missing")
    if metrics and review.reel_url:
        work = Path(tempfile.mkdtemp(prefix="afefehub-meta-"))
        try:
            meta = reel_metadata(review.reel_url, work)
            row.update(
                ig_likes=meta.like_count if meta.like_count is not None else "",
                ig_comments=meta.comment_count if meta.comment_count is not None else "",
                ig_views=meta.view_count if meta.view_count is not None else "",
            )
        except DownloadError as err:
            flags.append(f"reel unavailable: {str(err)[:80]}")
        finally:
            shutil.rmtree(work, ignore_errors=True)
    match = _closest(review)
    if match is not None:
        row.update(
            closest_review=match.review_id,
            match_audio=match.audio,
            match_video=match.video,
            match_text=match.text,
        )
        if fpcheck.is_similar(match):
            flags.append("similar to an existing review")
        elif fpcheck.is_lookalike(match):
            flags.append("video looks like an existing review")
    row["flags"] = "; ".join(flags)
    return row


def cmd_export(args) -> int:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    # Every entry goes in the sheet, unverified reels included: settle only acts on rows a
    # person has seen, and an author may still verify between this export and the settle.
    entries = rstore.list_window(args.window)
    unverified = sum(1 for e in entries if e.kind == "reel_unverified")
    if not entries:
        print(f"no entries in {args.window}")
        return 0
    counts: dict[str, int] = {}
    for e in entries:
        counts[e.phone_hash] = counts.get(e.phone_hash, 0) + 1
    wb = Workbook()
    summary = wb.active
    summary.title = "Summary"
    summary.append(["group", "pool_ngn", "entries", "points", "value_at_full_rate", "rate"])
    per_point = get_settings().ngn_per_point
    for group in rules.GROUPS:
        rows = [e for e in entries if e.group == group]
        ws = wb.create_sheet(rules.GROUP_LABELS[group])
        ws.append(COLUMNS)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for i, e in enumerate(sorted(rows, key=lambda x: (x.phone_hash, x.entered_at)), 1):
            print(f"  {group}: {i}/{len(rows)} {e.review_id}", file=sys.stderr)
            ws.append(
                [_row(e, dynamo.get_review(e.review_id), counts, args.metrics)[c] for c in COLUMNS]
            )
        live = [e for e in rows if e.status != "voided"]
        points = sum(e.points for e in live)
        pool = rules.pools_ngn()[group]
        rate = min(per_point, pool / points) if points else per_point
        summary.append([group, pool, len(live), points, points * per_point, round(rate, 2)])
    out = Path(args.out or f"payout-{args.window}.xlsx")
    wb.save(out)
    print(
        f"wrote {out} ({len(entries)} entries, {unverified} reels not yet verified). Fill "
        "`decision` (approve/void/ban) and `note`."
    )
    return 0


def _read_decisions(sheet: Path) -> dict[str, tuple[str, str]]:
    from openpyxl import load_workbook

    wb = load_workbook(sheet, read_only=True)
    out: dict[str, tuple[str, str]] = {}
    for ws in wb.worksheets:
        rows = ws.iter_rows(values_only=True)
        header = next(rows, None)
        if not header or "review_id" not in header:
            continue
        idx = {name: i for i, name in enumerate(header)}
        for r in rows:
            rid = r[idx["review_id"]]
            if not rid:
                continue
            decision = r[idx["decision"]] if "decision" in idx else ""
            note = r[idx["note"]] if "note" in idx else ""
            out[str(rid)] = (str(decision or ""), str(note or ""))
    return out


def _ban_reason(note: str) -> str:
    first = (note or "").strip().split(" ", 1)[0].lower().strip(":,.")
    return first if first in bans.REASONS else "spam"


def cmd_settle(args) -> int:
    entries = [e for e in rstore.list_window(args.window) if e.status != "paid"]
    decisions = _read_decisions(Path(args.sheet))
    for d, _ in decisions.values():
        settle.normalise_decision(d)  # fail on a typo before anything is written
    changed, to_ban, missing = settle.apply_decisions(entries, decisions)
    groups, payees = settle.compute(entries)

    print(f"window {args.window}: {len(entries)} open entries")
    for g in groups.values():
        print(
            f"  {g.group:<12} pool {rules.naira(g.pool_ngn):>12}  points {g.points:>6}  "
            f"rate {g.rate_ngn:8.2f}/pt  pays {rules.naira(g.paid_ngn):>12}"
        )
    voided = sum(1 for e in changed if e.status == "voided")
    print(f"  approved {len(changed) - voided}, voided {voided}, reviewers to ban {len(to_ban)}")
    if missing:
        print(
            f"  {len(missing)} entries are not in the sheet (entered or changed after the "
            "export) and stay open; export again and settle them separately:"
        )
        for e in missing:
            print(f"    {e.review_id}  {e.group}  {e.kind}  {e.points} pts")

    transfers, missing = [], []
    for p in payees:
        payee = rstore.get_payee(p.phone_hash)
        row = {
            "phone_hash": p.phone_hash,
            "phone": p.phone or "",
            "method": payee.method if payee else "",
            "bank_name": (payee.bank_name or "") if payee else "",
            "account_number": (payee.account_number or "") if payee else "",
            "account_name": (payee.account_name or "") if payee else "",
            "amount_ngn": p.amount_ngn,
            "window": args.window,
            "review_ids": " ".join(p.review_ids),
        }
        (transfers if payee and payee.complete else missing).append(row)
    total = sum(r["amount_ngn"] for r in transfers + missing)
    print(
        f"  {len(transfers)} payees ready, {len(missing)} without payout details; "
        f"total {rules.naira(total)}"
    )

    if not args.apply:
        print("dry run: nothing written. Re-run with --apply.")
        return 0
    ban_notes: dict[str, str] = {}
    for e in entries:
        decision, note = decisions.get(e.review_id, ("", ""))
        if decision.strip().lower() == "ban":
            ban_notes.setdefault(e.phone_hash, note)
    for h in to_ban:
        note = ban_notes.get(h, "")
        bans.ban(h, _ban_reason(note), note=note, by="payout-review")
    for e in changed:
        rstore.put_entry(e)
    rstore.put_payrun(
        args.window,
        {
            "settled_at": now_iso(),
            "groups": {g.group: vars(g) for g in groups.values()},
            "payees": len(payees),
            "total_ngn": total,
        },
    )
    out = Path(f"transfers-{args.window}.csv")
    _write_csv(out, transfers)
    print(f"wrote {out}: make these transfers, then run mark-paid with it.")
    if missing:
        miss = Path(f"missing-details-{args.window}.csv")
        _write_csv(miss, missing)
        print(f"wrote {miss}: these payees have not sent bank details yet.")
    return 0


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TRANSFER_COLUMNS)
        w.writeheader()
        w.writerows(rows)


def cmd_mark_paid(args) -> int:
    with Path(args.csv).open() as f:
        rows = list(csv.DictReader(f))
    label = rules.window_label(args.window)
    s = get_settings()
    for row in rows:
        h = row["phone_hash"]
        ids = set(row["review_ids"].split())
        entries = [
            e for e in rstore.list_entries(h)
            if e.review_id in ids and e.window == args.window and e.status == "approved"
        ]  # fmt: skip
        amount = sum(e.amount_ngn or 0 for e in entries)
        payee = rstore.get_payee(h)
        dest = payee.masked() if payee else "your account"
        print(f"  {h[:8]} {rules.naira(amount)} -> {dest} ({len(entries)} entries)")
        if not args.apply:
            continue
        for e in entries:
            e.status = "paid"
            e.paid_at = now_iso()
            rstore.put_entry(e)
        phone = row.get("phone") or (entries[0].phone if entries else None)
        if phone and entries:
            name = (payee.account_name or "there").split()[0] if payee else "there"
            wa.send_template(
                phone, s.wa_template_payout_sent, [name, rules.naira(amount), label, dest]
            )
    if not args.apply:
        print("dry run: nothing written. Re-run with --apply.")
        return 0
    run = rstore.get_payrun(args.window) or {}
    run["paid_at"] = now_iso()
    rstore.put_payrun(args.window, run)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("export", help="spreadsheet of a window's entries")
    ex.add_argument("--window", required=True, help="yyyy-mm")
    ex.add_argument("--out")
    ex.add_argument(
        "--no-metrics", dest="metrics", action="store_false", help="skip Instagram counts"
    )
    st = sub.add_parser("settle", help="apply decisions and compute transfers")
    st.add_argument("--window", required=True)
    st.add_argument("--sheet", required=True)
    st.add_argument("--apply", action="store_true")
    mp = sub.add_parser("mark-paid", help="record transfers and notify payees")
    mp.add_argument("--window", required=True)
    mp.add_argument("--csv", required=True)
    mp.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    return {"export": cmd_export, "settle": cmd_settle, "mark-paid": cmd_mark_paid}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
