"""Duplicate detection for reviews: exact media hashes, audio (Chromaprint), video (per-frame
dHash) and transcript (MinHash) fingerprints, an OpenSearch index to find candidates, and
scores to decide whether a new submission duplicates, or is too similar to, an existing review.
"""
