"""Write the crawlable pages to the site bucket and keep them in step with the data.

Called on publish (one business re-rendered, its hubs, sitemaps and llms.txt refreshed), on
erasure (the business re-rendered without the erased review, or its page deleted), and nightly
by scripts/render_site.py (everything re-rendered, stale pages pruned). Nothing here may fail a
publish or an erasure: the callers catch and log, and the nightly run heals what was missed.

Bucket layout (all owned by the backend; the frontend deploy must exclude these):
  b/<slug>.html, b/<slug>.md          business pages
  places.html, places/<...>.html|.md  hub pages
  sitemap.xml, sitemaps/*.xml         sitemaps
  llms.txt, llms-full.txt             AI-agent index
  <indexnow-key>.txt                  IndexNow key file
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import boto3
import httpx

from app.config import get_settings
from app.models import now_iso
from app.seo import render
from app.seo.model import BusinessPage, Hub, Listing, build_hubs
from app.seo.slugs import is_demo
from app.store import dynamo

log = logging.getLogger(__name__)

PAGE_CACHE = "public, max-age=300, s-maxage=86400"  # invalidated on change
SHARED_CACHE = "public, max-age=300, s-maxage=900"  # hubs, sitemaps, llms: short edge TTL
HTML = "text/html; charset=utf-8"
MD = "text/markdown; charset=utf-8"
XML = "application/xml; charset=utf-8"
TXT = "text/plain; charset=utf-8"
OWNED_PREFIXES = ("b/", "places/")
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
# Only the local preview (scripts/render_site.py --fixture) renders the fictional demo rows.
ALLOW_DEMO = False


def _publishable(business_id: str) -> bool:
    return ALLOW_DEMO or not is_demo(business_id)


class SiteWriter(Protocol):
    def put(self, key: str, body: str, content_type: str, cache_control: str) -> None: ...
    def delete(self, key: str) -> None: ...
    def list(self, prefix: str) -> list[str]: ...
    def invalidate(self, paths: list[str]) -> None: ...


class S3SiteWriter:
    def __init__(self, bucket: str, distribution_id: str = ""):
        s = get_settings()
        self.bucket = bucket
        self.distribution_id = distribution_id
        self.s3 = boto3.client("s3", region_name=s.aws_region)
        self.cf = boto3.client("cloudfront") if distribution_id else None

    def put(self, key: str, body: str, content_type: str, cache_control: str) -> None:
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType=content_type,
            CacheControl=cache_control,
        )

    def delete(self, key: str) -> None:
        self.s3.delete_object(Bucket=self.bucket, Key=key)

    def list(self, prefix: str) -> list[str]:
        keys: list[str] = []
        for page in self.s3.get_paginator("list_objects_v2").paginate(
            Bucket=self.bucket, Prefix=prefix
        ):
            keys.extend(o["Key"] for o in page.get("Contents", []))
        return keys

    def invalidate(self, paths: list[str]) -> None:
        if not self.cf or not paths:
            return
        self.cf.create_invalidation(
            DistributionId=self.distribution_id,
            InvalidationBatch={
                "Paths": {"Quantity": len(paths), "Items": paths},
                "CallerReference": f"afefehub-{datetime.now(UTC).timestamp()}",
            },
        )


class DirSiteWriter:
    """Writes the same layout to a local folder (scripts/render_site.py --out, tests)."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.invalidated: list[str] = []

    def put(self, key: str, body: str, content_type: str, cache_control: str) -> None:
        p = self.root / key
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    def delete(self, key: str) -> None:
        (self.root / key).unlink(missing_ok=True)

    def list(self, prefix: str) -> list[str]:
        base = self.root / prefix
        if not base.exists():
            return []
        return sorted(str(p.relative_to(self.root)) for p in base.rglob("*") if p.is_file())

    def invalidate(self, paths: list[str]) -> None:
        self.invalidated.extend(paths)


@lru_cache
def default_writer() -> SiteWriter | None:
    s = get_settings()
    if not s.site_bucket:
        return None
    return S3SiteWriter(s.site_bucket, s.cloudfront_distribution_id)


# --------------------------------------------------------------------------- data
def load_page(business_id: str) -> BusinessPage | None:
    if not _publishable(business_id):
        return None
    b = dynamo.get_business(business_id)
    if not b:
        return None
    reviews = [r for r in dynamo.list_reviews(business_id, limit=1000) if r.status == "published"]
    reviews.sort(key=lambda r: r.created_at, reverse=True)
    return BusinessPage(business=b, summary=dynamo.get_summary(business_id), reviews=reviews)


def load_listings() -> list[Listing]:
    return [
        Listing(business=b, summary=dynamo.get_summary(b.business_id))
        for b in dynamo.list_all_businesses()
        if b.review_count > 0 and _publishable(b.business_id)
    ]


# ------------------------------------------------------------------------- keys
def page_key(path: str, ext: str) -> str:
    """/b/x -> b/x.html; /places/ng/lagos -> places/ng/lagos.html; /places -> places.html."""
    return f"{path.lstrip('/')}.{ext}"


def key_path(key: str) -> str:
    """Inverse of page_key, for invalidation and IndexNow: b/x.html -> /b/x."""
    stem = key.rsplit(".", 1)[0]
    return "/" + stem


def _related(page: BusinessPage, hubs: dict[str, Hub]) -> list[Listing]:
    for path in reversed(page.hub_paths()[1:]):
        hub = hubs.get(path)
        if hub and len(hub.listings) > 1:
            return hub.listings
    return []


def _write_business(w: SiteWriter, page: BusinessPage, hubs: dict[str, Hub]) -> str:
    out = render.render_business(page, _related(page, hubs))
    w.put(page_key(page.path, "html"), out.html, HTML, PAGE_CACHE)
    w.put(page_key(page.path, "md"), out.md, MD, PAGE_CACHE)
    return out.md


def _write_hub(w: SiteWriter, hub: Hub) -> None:
    out = render.render_hub(hub)
    w.put(page_key(hub.path, "html"), out.html, HTML, SHARED_CACHE)
    w.put(page_key(hub.path, "md"), out.md, MD, SHARED_CACHE)


def _write_shared(w: SiteWriter, listings: list[Listing], hubs: dict[str, Hub]) -> None:
    for key, xml in render.render_sitemaps(listings, hubs).items():
        w.put(key, xml, XML, SHARED_CACHE)
    w.put("llms.txt", render.render_llms(listings, hubs, now_iso()[:10]), TXT, SHARED_CACHE)


def _expected_keys(listings: list[Listing], hubs: dict[str, Hub]) -> set[str]:
    keys: set[str] = set()
    for li in listings:
        keys |= {page_key(li.path, "html"), page_key(li.path, "md")}
    for h in hubs.values():
        keys |= {page_key(h.path, "html"), page_key(h.path, "md")}
    return keys


def _prune(w: SiteWriter, expected: set[str]) -> list[str]:
    """Delete backend-owned pages that no longer correspond to a business or hub."""
    removed = []
    for prefix in OWNED_PREFIXES:
        for key in w.list(prefix):
            if key not in expected:
                w.delete(key)
                removed.append(key)
    return removed


def ping_indexnow(urls: Iterable[str]) -> None:
    s = get_settings()
    urls = sorted(set(urls))
    if not s.indexnow_key or not urls or s.env != "prod":
        return
    site = s.public_site_url.rstrip("/")
    try:
        httpx.post(
            INDEXNOW_ENDPOINT,
            json={
                "host": site.split("://", 1)[-1],
                "key": s.indexnow_key,
                "keyLocation": f"{site}/{s.indexnow_key}.txt",
                "urlList": urls[:10000],
            },
            timeout=5,
        ).raise_for_status()
    except Exception:  # noqa: BLE001
        log.warning("IndexNow ping failed for %d urls", len(urls), exc_info=True)


# ------------------------------------------------------------------- entrypoints
def publish_business_page(business_id: str, writer: SiteWriter | None = None) -> bool:
    """Re-render one business (after a publish or an erasure rebuild) plus its hubs and the
    shared indexes. Returns False when page publishing is not configured."""
    w = writer or default_writer()
    if w is None:
        return False
    page = load_page(business_id)
    if page is None or not page.reviews:
        return remove_business_page(business_id, writer=w)
    listings = load_listings()
    hubs = build_hubs(listings)
    _write_business(w, page, hubs)
    for path in page.hub_paths():
        if path in hubs:
            _write_hub(w, hubs[path])
    _write_shared(w, listings, hubs)
    w.invalidate([page.path, f"{page.path}.md"])
    site = get_settings().public_site_url.rstrip("/")
    ping_indexnow([f"{site}{page.path}", *(f"{site}{p}" for p in page.hub_paths() if p in hubs)])
    log.info("rendered page %s", page.path)
    return True


def remove_business_page(business_id: str, writer: SiteWriter | None = None) -> bool:
    """After a business is deleted (its last review erased): drop its page and any hub that is
    now empty, refresh the others and the shared indexes. Works without the deleted record:
    whatever no longer matches a business or hub is pruned."""
    w = writer or default_writer()
    if w is None:
        return False
    listings = load_listings()
    hubs = build_hubs(listings)
    for hub in hubs.values():
        _write_hub(w, hub)
    removed = _prune(w, _expected_keys(listings, hubs))
    _write_shared(w, listings, hubs)
    paths = sorted({key_path(k) for k in removed} | {f"{key_path(k)}.md" for k in removed})
    w.invalidate(paths)
    site = get_settings().public_site_url.rstrip("/")
    ping_indexnow(f"{site}{key_path(k)}" for k in removed if k.endswith(".html"))
    log.info("removed page(s) for %s: %s", business_id, removed)
    return True


def render_all(writer: SiteWriter | None = None) -> dict:
    """Everything, from scratch: every business page, every hub, sitemaps, llms.txt,
    llms-full.txt and the IndexNow key file; then prune what no longer exists."""
    w = writer or default_writer()
    if w is None:
        raise RuntimeError("SITE_BUCKET is not set; pass a writer (e.g. DirSiteWriter)")
    s = get_settings()
    listings = load_listings()
    hubs = build_hubs(listings)
    markdown: list[str] = []
    for li in sorted(listings, key=lambda x: (-x.business.review_count, x.business.name)):
        page = load_page(li.business.business_id)
        if page is None or not page.reviews:
            continue
        markdown.append(_write_business(w, page, hubs))
    for hub in hubs.values():
        _write_hub(w, hub)
    _write_shared(w, listings, hubs)
    w.put("llms-full.txt", render.render_llms_full(markdown), TXT, SHARED_CACHE)
    if s.indexnow_key:
        w.put(f"{s.indexnow_key}.txt", s.indexnow_key, TXT, SHARED_CACHE)
    removed = _prune(w, _expected_keys(listings, hubs))
    w.invalidate(["/b/*", "/places*", "/sitemap*", "/llms*"])
    return {"businesses": len(markdown), "hubs": len(hubs), "pruned": removed}
