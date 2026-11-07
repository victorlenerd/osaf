"""Repair businesses stored with a country name ("NIGERIA") instead of its ISO alpha-2 code.

    python scripts/fix_countries.py            # dry run: list what would change
    python scripts/fix_countries.py --apply    # fix DynamoDB, the search index and the pages

Older Google Places lookups stored the country's long name, which the agent upper-cased. The
site, /api/top, the MCP server and the /places hubs all expect the two-letter code. After the
fix each business is re-indexed and its page re-rendered; then every page is re-rendered so the
hub built from the bad value (e.g. /places/nigeria) is pruned.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.countries import country_code  # noqa: E402
from app.seo import site  # noqa: E402
from app.store import dynamo, opensearch  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write the fixes (default: dry run)")
    args = ap.parse_args()

    bad, unknown = [], []
    for b in dynamo.list_all_businesses():
        code = country_code(b.country)
        if code == b.country:
            continue
        (bad if code else unknown).append((b, code))
    for b, code in bad:
        print(
            f"{'fix' if args.apply else 'would fix'} {b.business_id} {b.name!r}: "
            f"{b.country!r} -> {code!r}"
        )
    for b, _ in unknown:
        print(
            f"UNKNOWN country {b.country!r} on {b.business_id} {b.name!r}: fix by hand",
            file=sys.stderr,
        )
    if not args.apply:
        print(f"dry run: {len(bad)} to fix, {len(unknown)} unknown")
        return 0

    for b, code in bad:
        dynamo.set_business_country(b.business_id, code)
        fixed = dynamo.get_business(b.business_id)
        try:
            opensearch.upsert_business(fixed, dynamo.get_summary(b.business_id))
        except Exception as e:  # noqa: BLE001
            print(f"  search index not updated for {b.business_id}: {e!r}", file=sys.stderr)
    if bad and site.default_writer() is not None:
        print(site.render_all())
    print(f"fixed {len(bad)}, unknown {len(unknown)}")
    return 1 if unknown else 0


if __name__ == "__main__":
    sys.exit(main())
