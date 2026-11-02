"""Erase everything Afefehub holds about one WhatsApp number, for requests that arrive by
email rather than through the "delete my data" chat command.

    python scripts/delete_reviewer.py 2348012345678          # show what would be removed
    python scripts/delete_reviewer.py 2348012345678 --yes    # remove it

The number is the WhatsApp wa_id: country code and digits, no "+" or spaces (a "+" or spaces
are stripped). Runs with the same AWS credentials and .env the backend uses. Give the
reviewer the printed reference; it is also stored as an ERASURE#<ref> receipt in DynamoDB.
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
    ap.add_argument("phone", help="WhatsApp number as a wa_id, e.g. 2348012345678")
    ap.add_argument("--yes", action="store_true", help="actually erase (default: preview only)")
    args = ap.parse_args()

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

    report = erase.erase_reviewer(phone)
    print(
        f"erased: {report.reviews} reviews, {report.submissions} submissions, "
        f"{report.objects} S3 objects, {report.points_forfeited} points"
    )
    for bid in report.businesses_rebuilt:
        print(f"  rebuilt  {bid}")
    for bid in report.businesses_removed:
        print(f"  removed  {bid}")
    for err in report.errors:
        print(f"  ERROR    {err}", file=sys.stderr)
    print(f"reference: {report.reference}")
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
