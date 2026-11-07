"""Ban a reviewer for spam or abuse, or lift a ban.

    python scripts/ban_reviewer.py 2348012345678 --reason spam --note "same reel 5x"   # preview
    python scripts/ban_reviewer.py 2348012345678 --reason spam --hide-reviews --yes
    python scripts/ban_reviewer.py --review 01JC... --reason duplicate --yes    # by review id
    python scripts/ban_reviewer.py 2348012345678 --unban [--unhide-reviews] --yes
    python scripts/ban_reviewer.py --list

A ban stops the number at intake and at publish, voids every payout entry not yet paid,
withdraws open ENTER offers, and refuses reels from Instagram accounts verified to the
number. With --hide-reviews all of the reviewer's reviews are hidden from the site and the
businesses they were on are rebuilt. The ban is stored under the number's keyed hash and
survives "delete my data".
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.moderation import bans  # noqa: E402
from app.pii import phone_hash  # noqa: E402
from app.store import dynamo  # noqa: E402
from app.store import rewards_store as rstore  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("phone", nargs="?", help="WhatsApp number as a wa_id, e.g. 2348012345678")
    ap.add_argument("--review", help="ban the author of this review id instead")
    ap.add_argument("--reason", choices=bans.REASONS, default="spam")
    ap.add_argument("--note", default="")
    ap.add_argument("--hide-reviews", action="store_true")
    ap.add_argument("--unban", action="store_true")
    ap.add_argument("--unhide-reviews", action="store_true")
    ap.add_argument("--list", action="store_true", help="list current bans and exit")
    ap.add_argument("--yes", action="store_true", help="actually do it (default: preview)")
    args = ap.parse_args()

    if args.list:
        for b in sorted(rstore.list_bans(), key=lambda x: x.banned_at):
            print(
                f"{b.banned_at}  {b.phone_hash[:8]}  {b.reason:<9} hidden={b.reviews_hidden} "
                f"voided={b.entries_voided}  {b.note}"
            )
        return 0

    if args.review:
        review = dynamo.get_review(args.review)
        if review is None:
            print(f"no review {args.review}", file=sys.stderr)
            return 2
        h = review.reviewer_phone_hash
    elif args.phone:
        h = phone_hash(re.sub(r"[^\d]", "", args.phone))
    else:
        ap.error("give a phone number, --review or --list")

    existing = rstore.get_ban(h)
    reviews = dynamo.list_all_reviews_by_reviewer(h)
    open_entries = [e for e in rstore.list_entries(h) if e.status in ("entered", "approved")]
    print(
        f"reviewer {h[:8]}: {len(reviews)} reviews "
        f"({sum(r.status == 'published' for r in reviews)} published), "
        f"{len(open_entries)} open payout entries, "
        f"{'already banned (' + existing.reason + ')' if existing else 'not banned'}"
    )
    if not args.yes:
        print("preview only; re-run with --yes")
        return 0
    if args.unban:
        b = bans.unban(h, unhide_reviews=args.unhide_reviews)
        print("unbanned" if b else "was not banned")
        return 0
    b = bans.ban(h, args.reason, note=args.note, hide_reviews=args.hide_reviews)
    print(
        f"banned {h[:8]} ({b.reason}): {b.entries_voided} entries voided, "
        f"{b.reviews_hidden} reviews hidden, Instagram accounts: {', '.join(b.ig_usernames) or '-'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
