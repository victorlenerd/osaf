"""Webhook endpoint for the WhatsApp Cloud API.

GET  verifies the subscription (hub.challenge echo).
POST validates X-Hub-Signature-256, dedupes by message id, acks fast and processes in the
background so Meta never retries a slow request.
"""

from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request, Response

from app.config import get_settings
from app.pipeline.runner import process_inbound
from app.store import dynamo

log = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks/whatsapp", tags=["whatsapp"])


@router.get("")
def verify(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_token == get_settings().whatsapp_verify_token:
        return Response(content=hub_challenge or "", media_type="text/plain")
    raise HTTPException(status_code=403, detail="verification failed")


def _valid_signature(raw: bytes, header: str | None) -> bool:
    s = get_settings()
    secret = s.meta_app_secret
    if not secret:
        # Only a local dev box may run unsigned. Prod cannot start without the secret
        # (app/config.py), and any other environment fails closed here.
        if s.env == "dev":
            log.warning("META_APP_SECRET not set; accepting unsigned webhook (ENV=dev only)")
            return True
        log.error("META_APP_SECRET not set; rejecting webhook")
        return False
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[7:])


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
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            if value.get("messaging_product") != "whatsapp":
                continue
            contacts = {
                c.get("wa_id"): c.get("profile", {}).get("name") for c in value.get("contacts", [])
            }
            for msg in value.get("messages", []):
                wamid = msg.get("id")
                if not wamid or not dynamo.claim_wa_message(wamid):
                    continue
                phone = msg.get("from")
                background.add_task(process_inbound, phone, msg, contacts.get(phone))
                queued += 1
    return {"status": "ok", "queued": queued}
