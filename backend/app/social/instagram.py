"""Instagram Content Publishing API: carousel of images -> published post.

Flow (https://developers.facebook.com/docs/instagram-platform/content-publishing):
  1. POST /{ig-user-id}/media  {image_url, is_carousel_item=true}   -> child container, per image
  2. POST /{ig-user-id}/media  {media_type=CAROUSEL, children, caption} -> carousel container
  3. GET  /{container}?fields=status_code                           -> poll until FINISHED
  4. POST /{ig-user-id}/media_publish {creation_id}                 -> media id
Images must be JPEG at a public URL (a presigned S3 URL works) with an aspect ratio between
4:5 and 1.91:1; a carousel holds 2 to 10 items; the account may publish 50 posts per 24 h.
Same httpx style as app/whatsapp/client.py. Nothing here retries a publish: a failed
media_publish is reported, never repeated blindly, so a post cannot go out twice.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.config import Settings, get_settings

log = logging.getLogger(__name__)

MIN_CHILDREN, MAX_CHILDREN = 2, 10
FINISHED, IN_PROGRESS = "FINISHED", "IN_PROGRESS"


class InstagramPublishError(RuntimeError):
    pass


def _graph_error(r: httpx.Response) -> str:
    try:
        err = r.json().get("error") or {}
        msg = err.get("message", r.text[:300])
        return f"{r.status_code} {err.get('type', '')} {err.get('code', '')}: {msg}"
    except ValueError:
        return f"{r.status_code}: {r.text[:300]}"


class InstagramClient:
    def __init__(
        self,
        user_id: str,
        token: str,
        *,
        api_version: str = "v21.0",
        base: str = "https://graph.facebook.com",
        timeout: float = 30,
    ):
        if not user_id or not token:
            raise InstagramPublishError("IG_USER_ID and IG_ACCESS_TOKEN are required")
        self.user_id = user_id
        self._token = token
        self.base = f"{base.rstrip('/')}/{api_version}"
        self.timeout = timeout

    # ---------------------------------------------------------------- transport
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    def _get(self, path: str, params: dict | None = None) -> dict:
        r = httpx.get(
            f"{self.base}/{path}", params=params, headers=self._headers(), timeout=self.timeout
        )
        if r.status_code >= 400:
            raise InstagramPublishError(f"GET {path} failed: {_graph_error(r)}")
        return r.json()

    def _post(self, path: str, data: dict) -> dict:
        r = httpx.post(
            f"{self.base}/{path}", data=data, headers=self._headers(), timeout=self.timeout
        )
        if r.status_code >= 400:
            raise InstagramPublishError(f"POST {path} failed: {_graph_error(r)}")
        return r.json()

    # -------------------------------------------------------------- read-only
    def me(self) -> dict:
        """{id, username, name} of the account the token posts as (preflight)."""
        return self._get(self.user_id, {"fields": "id,username,name"})

    def publishing_limit(self) -> dict:
        """{quota_usage, config: {quota_total, quota_duration}} for the rolling 24 h window."""
        data = self._get(
            f"{self.user_id}/content_publishing_limit", {"fields": "quota_usage,config"}
        )
        rows = data.get("data") or [{}]
        return rows[0]

    def container_status(self, container_id: str) -> tuple[str, str]:
        data = self._get(container_id, {"fields": "status_code,status"})
        return str(data.get("status_code", "")), str(data.get("status", ""))

    def permalink(self, media_id: str) -> str:
        return str(self._get(media_id, {"fields": "permalink"}).get("permalink", ""))

    # ----------------------------------------------------------------- writes
    def create_image_container(self, image_url: str, *, is_carousel_item: bool = True) -> str:
        data: dict[str, Any] = {"image_url": image_url}
        if is_carousel_item:
            data["is_carousel_item"] = "true"
        return str(self._post(f"{self.user_id}/media", data)["id"])

    def create_carousel_container(self, children: list[str], caption: str) -> str:
        if not MIN_CHILDREN <= len(children) <= MAX_CHILDREN:
            raise InstagramPublishError(
                f"a carousel needs {MIN_CHILDREN} to {MAX_CHILDREN} items, got {len(children)}"
            )
        data = {"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption}
        return str(self._post(f"{self.user_id}/media", data)["id"])

    def wait_finished(
        self,
        container_id: str,
        *,
        timeout_s: float = 300,
        poll_s: float = 5,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        deadline = time.monotonic() + timeout_s
        while True:
            code, status = self.container_status(container_id)
            if code == FINISHED:
                return
            if code and code != IN_PROGRESS:  # ERROR, EXPIRED, PUBLISHED
                raise InstagramPublishError(f"container {container_id} is {code}: {status}")
            if time.monotonic() >= deadline:
                raise InstagramPublishError(
                    f"container {container_id} still {code or 'pending'} after {timeout_s:.0f}s"
                )
            sleep(poll_s)

    def publish(self, creation_id: str) -> str:
        return str(self._post(f"{self.user_id}/media_publish", {"creation_id": creation_id})["id"])

    # -------------------------------------------------------------- messaging
    # Instagram messaging (instagram_business_manage_messages): the webhook gives a sender's
    # Instagram-scoped id; the profile lookup turns it into a username, and replies go out
    # through /{ig-user-id}/messages.
    def username_of(self, igsid: str) -> str:
        return str(self._get(igsid, {"fields": "username"}).get("username", "")).lower()

    def send_dm(self, igsid: str, text: str) -> None:
        self._post(
            f"{self.user_id}/messages",
            {
                "recipient": json.dumps({"id": igsid}),
                "message": json.dumps({"text": text[:1000]}),
            },
        )


def client_from_settings(s: Settings | None = None) -> InstagramClient:
    s = s or get_settings()
    return InstagramClient(
        s.ig_user_id, s.ig_access_token, api_version=s.graph_api_version, base=s.ig_api_base
    )


def publish_carousel(
    client: InstagramClient,
    image_urls: list[str],
    caption: str,
    *,
    say: Callable[[str], None] = log.info,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[str, str]:
    """Upload, assemble, publish. Returns (media_id, permalink); permalink may be "" if that
    last read fails after the post is live."""
    if not MIN_CHILDREN <= len(image_urls) <= MAX_CHILDREN:
        raise InstagramPublishError(
            f"a carousel needs {MIN_CHILDREN} to {MAX_CHILDREN} items, got {len(image_urls)}"
        )
    children: list[str] = []
    for i, url in enumerate(image_urls, start=1):
        cid = client.create_image_container(url)
        client.wait_finished(cid, timeout_s=120, sleep=sleep)
        say(f"slide {i}/{len(image_urls)} container {cid} ready")
        children.append(cid)
    carousel = client.create_carousel_container(children, caption)
    client.wait_finished(carousel, sleep=sleep)
    say(f"carousel container {carousel} ready; publishing")
    media_id = client.publish(carousel)
    try:
        link = client.permalink(media_id)
    except InstagramPublishError as e:
        log.warning("published %s but could not read its permalink: %s", media_id, e)
        link = ""
    return media_id, link
