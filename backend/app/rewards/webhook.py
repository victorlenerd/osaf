"""Webhook for Instagram messaging (DMs to Afefehub's Instagram account), used only for
original-author verification codes. Same shape as the WhatsApp webhook: GET verifies the
subscription, POST checks the Meta app signature, dedupes by message id and processes in
the background."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request, Response

from app.config import get_settings
from app.rewards.verify import handle_ig_message
from app.store import rewards_store as rstore
from app.whatsapp.webhook import _valid_signature

log = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks/instagram", tags=["instagram"])


@router.get("")
def verify(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    token = get_settings().ig_verify_token
    if hub_mode == "subscribe" and token and hub_token == token:
        return Response(content=hub_challenge or "", media_type="text/plain")
    raise HTTPException(status_code=403, detail="verification failed")


def _process(igsid: str, text: str) -> None:
    try:
        outcome = handle_ig_message(igsid, text)
        log.info("instagram DM: %s", outcome)
    except Exception:  # noqa: BLE001
        log.exception("instagram DM handling failed")


@router.post("")
async def receive(
    request: Request,
    background: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None),
):
    raw = await request.body()
    if not _valid_signature(raw, x_hub_signature_256):
        raise HTTPException(status_code=403, detail="bad signature")
    payload = await request.json()
    queued = 0
    if payload.get("object") != "instagram":
        return {"status": "ignored", "queued": 0}
    for entry in payload.get("entry", []):
        for event in entry.get("messaging", []):
            message = event.get("message") or {}
            if message.get("is_echo") or not message.get("text"):
                continue
            mid = message.get("mid")
            igsid = (event.get("sender") or {}).get("id")
            if not mid or not igsid or not rstore.claim_ig_message(mid):
                continue
            background.add_task(_process, igsid, message["text"])
            queued += 1
    return {"status": "ok", "queued": queued}
