"""MinHash over word 5-shingles of a transcript, plus LSH band tokens for the index."""

from __future__ import annotations

import hashlib
import random
import re

NUM_PERM = 64
BANDS, ROWS = 16, 4  # 16 bands of 4 rows: pairs above ~0.5 Jaccard collide in some band
SHINGLE = 5
_PRIME = (1 << 61) - 1
_MAX = (1 << 32) - 1
_rng = random.Random(20261106)  # fixed: signatures must be comparable across deployments
_PERMS = [(_rng.randrange(1, _PRIME), _rng.randrange(0, _PRIME)) for _ in range(NUM_PERM)]
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def words(text: str) -> list[str]:
    return _WORD.findall((text or "").lower())


def shingles(text: str, k: int = SHINGLE) -> set[str]:
    w = words(text)
    if not w:
        return set()
    if len(w) < k:
        return {" ".join(w)}
    return {" ".join(w[i : i + k]) for i in range(len(w) - k + 1)}


def _h(s: str) -> int:
    return int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "big")


def minhash(text: str) -> list[int]:
    sh = shingles(text)
    if not sh:
        return []
    hashed = [_h(s) for s in sh]
    return [min(((a * x + b) % _PRIME) & _MAX for x in hashed) for a, b in _PERMS]


def jaccard(a: list[int], b: list[int]) -> float:
    """Estimated Jaccard similarity of the two shingle sets."""
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x == y for x, y in zip(a, b, strict=True)) / len(a)


def band_tokens(sig: list[int]) -> list[str]:
    if len(sig) != NUM_PERM:
        return []
    out = []
    for band in range(BANDS):
        chunk = ",".join(str(v) for v in sig[band * ROWS : (band + 1) * ROWS])
        out.append(f"t{band}x{_h(chunk):016x}")
    return out
