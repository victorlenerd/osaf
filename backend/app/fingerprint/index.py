"""OpenSearch `fingerprints` index: one document per published review, holding band tokens to
find candidate matches and the full fingerprint to score them. Every call is a no-op when
OpenSearch is not configured (local dev, tests)."""

from __future__ import annotations

import logging

from opensearchpy import RequestError

from app.config import get_settings
from app.fingerprint import text as text_fp
from app.fingerprint.score import informative
from app.models import Fingerprint
from app.store import opensearch

log = logging.getLogger(__name__)

MAX_DOC_TOKENS = 1200
MAX_QUERY_TOKENS = 400  # stay well under the default 1024 boolean clauses

INDEX_BODY = {
    "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
    "mappings": {
        "properties": {
            "review_id": {"type": "keyword"},
            "business_id": {"type": "keyword"},
            "phone_hash": {"type": "keyword"},
            "sha256": {"type": "keyword"},
            "created_at": {"type": "date"},
            "status": {"type": "keyword"},  # pending while its review is being published
            "a": {"type": "text", "analyzer": "whitespace", "norms": False},
            "v": {"type": "text", "analyzer": "whitespace", "norms": False},
            "t": {"type": "text", "analyzer": "whitespace", "norms": False},
            "fp": {"type": "object", "enabled": False},
        }
    },
}


def enabled() -> bool:
    return bool(get_settings().opensearch_endpoint)


def _index() -> str:
    return get_settings().fingerprint_index


def ensure_index() -> None:
    if not enabled():
        return
    c = opensearch.client()
    if c.indices.exists(index=_index()):
        return
    try:
        c.indices.create(index=_index(), body=INDEX_BODY)
    except RequestError as e:  # several workers race to create it at startup
        if e.error != "resource_already_exists_exception":
            raise


def _dedupe(tokens: list[str], cap: int) -> list[str]:
    return list(dict.fromkeys(tokens))[:cap]


def audio_tokens(values: list[int]) -> list[str]:
    # Drop the 4 lowest bits: re-encoding flips a few bits per value, mostly low ones.
    return [f"a{v >> 4:07x}" for v in values]


def video_tokens(hashes: list[int]) -> list[str]:
    # Four 16-bit bands per frame: two frames within 3 bits of each other share at least one.
    return [f"v{b}x{(h >> (16 * b)) & 0xFFFF:04x}" for h in informative(hashes) for b in range(4)]


def tokens(fp: Fingerprint, cap: int) -> dict[str, list[str]]:
    return {
        "a": _dedupe(audio_tokens(fp.audio), cap),
        "v": _dedupe(video_tokens(fp.video), cap),
        "t": _dedupe(text_fp.band_tokens(fp.text), cap),
    }


def put(
    review_id: str,
    business_id: str,
    phone_hash: str,
    created_at: str,
    fp: Fingerprint,
    *,
    status: str = "published",
) -> None:
    """Index a review's fingerprint. Publishing indexes it as "pending" before the review is
    stored (so a near-copy confirmed at the same moment sees it) and marks it published
    after; check.py ignores a pending entry left behind by a publish that crashed."""
    if not enabled():
        return
    toks = tokens(fp, MAX_DOC_TOKENS)
    doc = {
        "review_id": review_id,
        "business_id": business_id,
        "phone_hash": phone_hash,
        "sha256": fp.sha256,
        "created_at": created_at,
        "status": status,
        **{k: " ".join(v) for k, v in toks.items()},
        "fp": fp.model_dump(),
    }
    opensearch.client().index(index=_index(), id=review_id, body=doc, refresh=True)


def mark_published(review_id: str) -> None:
    if not enabled():
        return
    opensearch.client().update(
        index=_index(), id=review_id, body={"doc": {"status": "published"}}, refresh=True
    )


def delete(review_id: str) -> None:
    if not enabled():
        return
    opensearch.client().delete(index=_index(), id=review_id, ignore=[404], refresh=True)


def candidates(fp: Fingerprint, *, exclude: str | None = None, size: int = 20) -> list[dict]:
    """Documents that share an exact hash or enough band tokens with `fp`, each as
    {review_id, business_id, phone_hash, sha256, fp}. Deduplicated across the kinds."""
    if not enabled():
        return []
    c = opensearch.client()
    must_not = [{"term": {"review_id": exclude}}] if exclude else []
    queries = []
    if fp.sha256:
        queries.append({"term": {"sha256": fp.sha256}})
    minimum = {"a": "2%", "v": "1", "t": "1"}
    for field, toks in tokens(fp, MAX_QUERY_TOKENS).items():
        if toks:
            match = {"query": " ".join(toks), "minimum_should_match": minimum[field]}
            queries.append({"match": {field: match}})
    found: dict[str, dict] = {}
    for q in queries:
        body = {
            "size": size,
            "_source": [
                "review_id",
                "business_id",
                "phone_hash",
                "sha256",
                "fp",
                "status",
                "created_at",
            ],
            "query": {"bool": {"must": [q], "must_not": must_not}},
        }
        for hit in c.search(index=_index(), body=body)["hits"]["hits"]:
            src = hit["_source"]
            found.setdefault(src["review_id"], src)
    return list(found.values())
