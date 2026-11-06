"""Erase everything Afefehub holds about one WhatsApp number, for requests that arrive by
email rather than through the "delete my data" chat command.

    python scripts/delete_reviewer.py 2348012345678          # show what would be removed
    python scripts/delete_reviewer.py 2348012345678 --yes    # remove it
    python scripts/delete_reviewer.py --rebuild BIZ [BIZ…]   # finish a rebuild that failed

The number is the WhatsApp wa_id: country code and digits, no "+" or spaces (a "+" or spaces
are stripped). Runs with the same AWS credentials and .env the backend uses. Give the
reviewer the printed reference; it is also stored as an ERASURE#<ref> receipt in DynamoDB.

When an erasure reports a FAILED business, its reviews are already gone but its counters,
summary and search document still reflect them. The reviewer's conversation (and with it the
list of businesses to rebuild) is deleted at the end of the run, so re-running the erasure
will not pick it up: pass the ids from the FAILED lines (also under `businesses_failed` on the
receipt) to --rebuild instead.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pii import phone_label  # noqa: E402
from app.pipeline import erase  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("phone", nargs="?", help="WhatsApp number as a wa_id, e.g. 2348012345678")
    ap.add_argument("--yes", action="store_true", help="actually erase (default: preview only)")
    ap.add_argument(
        "--rebuild",
        nargs="+",
        metavar="BIZ",
        help="rebuild these business ids from their remaining reviews and exit",
    )
    args = ap.parse_args()

    if args.rebuild:
        if args.phone:
            ap.error("--rebuild takes business ids only, not a phone number")
        return _print_report(erase.rebuild_businesses(args.rebuild), erased=False)
    if not args.phone:
        ap.error("a phone number is required unless --rebuild is given")

    phone = re.sub(r"[^\d]", "", args.phone)
    if not 7 <= len(phone) <= 15:
        print(f"not a plausible phone number: {args.phone!r}", file=sys.stderr)
        return 2

    p = erase.preview(phone)
    print(
        f"{phone_label(phone)}: {p.reviews} published reviews, {p.submissions} submissions, "
        f"{p.points} points"
    )
    if not args.yes:
        print("preview only; re-run with --yes to erase")
        return 0

    return _print_report(erase.erase_reviewer(phone), erased=True)


def _print_report(report: erase.ErasureReport, *, erased: bool) -> int:
    if erased:
        print(
            f"erased: {report.reviews} reviews, {report.submissions} submissions, "
            f"{report.objects} S3 objects, {report.points_forfeited} points"
        )
    for bid in report.businesses_rebuilt:
        print(f"  rebuilt  {bid}")
    for bid in report.businesses_removed:
        print(f"  removed  {bid}")
    if report.businesses_failed:
        ids = " ".join(report.businesses_failed)
        for bid in report.businesses_failed:
            print(f"  FAILED   {bid}", file=sys.stderr)
        print(f"  retry the rebuild with: --rebuild {ids}", file=sys.stderr)
    for err in report.errors:
        print(f"  ERROR    {err}", file=sys.stderr)
    if erased:
        print(f"reference: {report.reference}")
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
