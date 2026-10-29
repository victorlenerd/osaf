"""Create the OpenSearch `businesses` index if it does not exist."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.store.opensearch import ensure_index  # noqa: E402

if __name__ == "__main__":
    ensure_index()
    print("index ready")
