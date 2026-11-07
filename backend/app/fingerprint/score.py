"""Pairwise similarity scores in 0..1 for each fingerprint kind."""

from __future__ import annotations

from app.fingerprint import text as text_fp

AUDIO_MAX_OFFSET = 120  # Chromaprint frames (~8/s): tolerate up to ~15 s of trimming
AUDIO_WINDOW = 480  # compare at most ~60 s of the shorter clip
AUDIO_MIN_OVERLAP = 40  # ~5 s
FRAME_MATCH_BITS = 10  # dHash Hamming distance that still counts as the same frame
MIN_INFORMATIVE_FRAMES = 3


def informative(hashes: list[int]) -> list[int]:
    """Drop near-uniform frames (black, white, fades, flat title cards): their dHash is close
    to all zeros or all ones whatever the video, so they would match across unrelated reels."""
    return [h for h in hashes if 6 <= h.bit_count() <= 58]


def audio_similarity(a: list[int], b: list[int]) -> float:
    """Best alignment of two Chromaprint fingerprints, as 0 (unrelated) .. 1 (identical).

    Unrelated audio agrees on about half of the bits by chance, so the matching-bit ratio r
    is rescaled as 2 * (r - 0.5)."""
    if len(a) < AUDIO_MIN_OVERLAP or len(b) < AUDIO_MIN_OVERLAP:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    a = a[:AUDIO_WINDOW]
    best = 0.0
    for offset in range(-AUDIO_MAX_OFFSET, AUDIO_MAX_OFFSET + 1):
        lo = max(0, -offset)
        hi = min(len(a), len(b) - offset)
        n = hi - lo
        if n < AUDIO_MIN_OVERLAP:
            continue
        diff = 0
        for i in range(lo, hi):
            diff += (a[i] ^ b[i + offset]).bit_count()
        r = 1 - diff / (32 * n)
        if r > best:
            best = r
    return max(0.0, min(1.0, 2 * (best - 0.5)))


def video_similarity(a: list[int], b: list[int]) -> float:
    """Share of the shorter clip's informative frames that have a near-identical frame in the
    other."""
    a, b = informative(a), informative(b)
    if len(a) < MIN_INFORMATIVE_FRAMES or len(b) < MIN_INFORMATIVE_FRAMES:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    hits = sum(1 for x in a if any((x ^ y).bit_count() <= FRAME_MATCH_BITS for y in b))
    return hits / len(a)


def text_similarity(a: list[int], b: list[int]) -> float:
    return text_fp.jaccard(a, b)
