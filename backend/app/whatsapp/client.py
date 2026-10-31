"""WhatsApp Cloud API: send text and fetch media the reviewer uploads."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from app.config import get_settings
from app.pii import phone_label

log = logging.getLogger(__name__)


def _base() -> str:
    s = get_settings()
    return f"https://graph.facebook.com/{s.graph_api_version}"


def _headers() -> dict:
    return {"Authorization": f"Bearer {get_settings().whatsapp_access_token}"}


def send_text(to: str, body: str, *, preview_url: bool = True) -> None:
    s = get_settings()
    if not s.whatsapp_access_token:
        log.info("[dry-run] -> %s: %d chars", phone_label(to), len(body))
        return
    r = httpx.post(
        f"{_base()}/{s.whatsapp_phone_number_id}/messages",
        headers=_headers(),
        json={
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"preview_url": preview_url, "body": body[:4096]},
        },
        timeout=20,
    )
    if r.status_code >= 400:
        log.error("send_text failed %s: %s", r.status_code, r.text[:300])


def mark_read(message_id: str) -> None:
    s = get_settings()
    if not s.whatsapp_access_token:
        return
    httpx.post(
        f"{_base()}/{s.whatsapp_phone_number_id}/messages",
        headers=_headers(),
        json={"messaging_product": "whatsapp", "status": "read", "message_id": message_id},
        timeout=10,
    )


def download_media(media_id: str, dest: Path) -> Path:
    """Two-step: resolve the media id to a short-lived URL, then fetch it with the same token."""
    meta = httpx.get(f"{_base()}/{media_id}", headers=_headers(), timeout=20)
    meta.raise_for_status()
    url = meta.json()["url"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", url, headers=_headers(), timeout=120) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    return dest
