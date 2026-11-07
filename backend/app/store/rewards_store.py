"""DynamoDB items for payouts, bans and duplicate locks (same single table as dynamo.py).

PK / SK layout
  RWD#<phone_hash>     ENTRY#<review_id>      PayoutEntry
                                              GSI1: WINDOW#<yyyy-mm>/<group>#<entered_at>
  RWD#<phone_hash>     OFFER#<review_id>      PayoutOffer (TTL: the ENTER question expires)
  RWD#<phone_hash>     PAYEE                  Payee (bank details or Amazon)
  RWD#<phone_hash>     IGLINK#<username>      reverse of IGLINK#, for erasure and bans
  IGCODE#<code>        META                   author-verification code (TTL)
  IGLINK#<username>    META                   Instagram account verified to one phone hash
  IGMSG#<mid>          META                   Instagram webhook dedupe (TTL 24h)
  MEDIA#<sha256>       META                   one published review per media file
  BAN#<phone_hash>     META                   Ban          GSI1: BANS/<banned_at>
  BANIG#<username>     META                   Instagram account of a banned reviewer
  PAYRUN#<yyyy-mm>     META                   settlement record of one payout window

Entries are keyed by the phone hash, not the number, so a ban or a review id (which only
carries the hash) reaches them; the entry and payee items hold the number for payment.
"""

from __future__ import annotations

import json
import time
from decimal import Decimal
from typing import Any

from botocore.exceptions import ClientError

from app.models import Ban, Payee, PayoutEntry, PayoutOffer, now_iso
from app.store.dynamo import _claim, _from_item, _table, _to_item

IG_MESSAGE_TTL = 86400
FAR_FUTURE = 10 * 365 * 86400


def _rwd(phone_hash: str) -> str:
    return f"RWD#{phone_hash}"


def _query_all(**kwargs: Any) -> list[dict]:
    out: list[dict] = []
    while True:
        r = _table().query(**kwargs)
        out.extend(r.get("Items", []))
        if "LastEvaluatedKey" not in r:
            return out
        kwargs["ExclusiveStartKey"] = r["LastEvaluatedKey"]


def _partition(phone_hash: str, prefix: str) -> list[dict]:
    return _query_all(
        KeyConditionExpression="PK = :p AND begins_with(SK, :s)",
        ExpressionAttributeValues={":p": _rwd(phone_hash), ":s": prefix},
    )


# ------------------------------------------------------------------------ entries
def put_entry(e: PayoutEntry, *, only_new: bool = False) -> bool:
    """Write an entry. With only_new, refuse (return False) when the review is already entered."""
    item = {
        "PK": _rwd(e.phone_hash),
        "SK": f"ENTRY#{e.review_id}",
        "GSI1PK": f"WINDOW#{e.window}",
        "GSI1SK": f"{e.group}#{e.entered_at}",
        **_to_item(e),
    }
    kwargs: dict[str, Any] = {"Item": item}
    if only_new:
        kwargs["ConditionExpression"] = "attribute_not_exists(PK)"
    try:
        _table().put_item(**kwargs)
        return True
    except ClientError as err:
        if err.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def get_entry(phone_hash: str, review_id: str) -> PayoutEntry | None:
    r = _table().get_item(Key={"PK": _rwd(phone_hash), "SK": f"ENTRY#{review_id}"})
    return PayoutEntry(**_from_item(r["Item"])) if "Item" in r else None


def list_entries(phone_hash: str) -> list[PayoutEntry]:
    return [PayoutEntry(**_from_item(i)) for i in _partition(phone_hash, "ENTRY#")]


def list_window(window: str) -> list[PayoutEntry]:
    items = _query_all(
        IndexName="GSI1",
        KeyConditionExpression="GSI1PK = :p",
        ExpressionAttributeValues={":p": f"WINDOW#{window}"},
    )
    return [PayoutEntry(**_from_item(i)) for i in items]


def delete_entry(phone_hash: str, review_id: str) -> None:
    _table().delete_item(Key={"PK": _rwd(phone_hash), "SK": f"ENTRY#{review_id}"})


# ------------------------------------------------------------------------- offers
def put_offer(phone_hash: str, o: PayoutOffer, ttl_seconds: int) -> None:
    o.expires_at = int(time.time()) + ttl_seconds
    _table().put_item(Item={"PK": _rwd(phone_hash), "SK": f"OFFER#{o.review_id}", **_to_item(o)})


def list_offers(phone_hash: str) -> list[PayoutOffer]:
    """Open offers only: DynamoDB deletes expired TTL items lazily, so filter here too."""
    now = int(time.time())
    offers = [PayoutOffer(**_from_item(i)) for i in _partition(phone_hash, "OFFER#")]
    return [o for o in offers if o.expires_at is None or o.expires_at > now]


def delete_offer(phone_hash: str, review_id: str) -> None:
    _table().delete_item(Key={"PK": _rwd(phone_hash), "SK": f"OFFER#{review_id}"})


# -------------------------------------------------------------------------- payee
def get_payee(phone_hash: str) -> Payee | None:
    r = _table().get_item(Key={"PK": _rwd(phone_hash), "SK": "PAYEE"})
    return Payee(**_from_item(r["Item"])) if "Item" in r else None


def put_payee(phone_hash: str, p: Payee) -> None:
    p.updated_at = now_iso()
    _table().put_item(Item={"PK": _rwd(phone_hash), "SK": "PAYEE", **_to_item(p)})


def delete_rewards_partition(phone_hash: str, keep) -> int:
    """Delete every RWD# item of one reviewer except those `keep(item)` returns True for."""
    n = 0
    for item in _partition(phone_hash, ""):
        if keep(_from_item(item) | {"SK": item["SK"]}):
            continue
        _table().delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
        n += 1
    return n


# --------------------------------------------------------- Instagram verification
def put_ig_code(code: str, record: dict, ttl_seconds: int) -> None:
    _table().put_item(
        Item={
            "PK": f"IGCODE#{code}",
            "SK": "META",
            "created_at": now_iso(),
            "expires_at": int(time.time()) + ttl_seconds,
            **record,
        }
    )


def get_ig_code(code: str) -> dict | None:
    r = _table().get_item(Key={"PK": f"IGCODE#{code}", "SK": "META"})
    if "Item" not in r:
        return None
    item = _from_item(r["Item"])
    if int(item.get("expires_at", 0)) <= int(time.time()):
        return None
    return item


def delete_ig_code(code: str) -> None:
    _table().delete_item(Key={"PK": f"IGCODE#{code}", "SK": "META"})


def get_ig_link(username: str) -> str | None:
    """The phone hash an Instagram account is verified to, if any."""
    r = _table().get_item(Key={"PK": f"IGLINK#{username.lower()}", "SK": "META"})
    return r["Item"].get("phone_hash") if "Item" in r else None


def claim_ig_link(username: str, phone_hash: str) -> bool:
    """Link an Instagram account to one reviewer. False when another reviewer holds it."""
    u = username.lower()
    try:
        _table().put_item(
            Item={
                "PK": f"IGLINK#{u}",
                "SK": "META",
                "phone_hash": phone_hash,
                "verified_at": now_iso(),
            },
            ConditionExpression="attribute_not_exists(PK) OR phone_hash = :h",
            ExpressionAttributeValues={":h": phone_hash},
        )
    except ClientError as err:
        if err.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise
    _table().put_item(Item={"PK": _rwd(phone_hash), "SK": f"IGLINK#{u}", "username": u})
    return True


def list_ig_links(phone_hash: str) -> list[str]:
    return [i["username"] for i in _partition(phone_hash, "IGLINK#")]


def delete_ig_link(username: str) -> None:
    _table().delete_item(Key={"PK": f"IGLINK#{username.lower()}", "SK": "META"})


def claim_ig_message(mid: str) -> bool:
    return _claim(f"IGMSG#{mid}", IG_MESSAGE_TTL)


# ----------------------------------------------------------------- media locks
def claim_media(sha256: str, review_id: str) -> bool:
    """One published review per media file (the exact-copy guard behind the fingerprints)."""
    return _claim(f"MEDIA#{sha256}", FAR_FUTURE, {"review_id": review_id})


def delete_media_claim(sha256: str) -> None:
    _table().delete_item(Key={"PK": f"MEDIA#{sha256}", "SK": "META"})


# --------------------------------------------------------------------------- bans
def get_ban(phone_hash: str) -> Ban | None:
    r = _table().get_item(Key={"PK": f"BAN#{phone_hash}", "SK": "META"})
    return Ban(**_from_item(r["Item"])) if "Item" in r else None


def put_ban(b: Ban) -> None:
    _table().put_item(
        Item={
            "PK": f"BAN#{b.phone_hash}",
            "SK": "META",
            "GSI1PK": "BANS",
            "GSI1SK": b.banned_at,
            **_to_item(b),
        }
    )
    for u in b.ig_usernames:
        _table().put_item(
            Item={"PK": f"BANIG#{u.lower()}", "SK": "META", "phone_hash": b.phone_hash}
        )


def delete_ban(b: Ban) -> None:
    for u in b.ig_usernames:
        _table().delete_item(Key={"PK": f"BANIG#{u.lower()}", "SK": "META"})
    _table().delete_item(Key={"PK": f"BAN#{b.phone_hash}", "SK": "META"})


def list_bans() -> list[Ban]:
    items = _query_all(
        IndexName="GSI1",
        KeyConditionExpression="GSI1PK = :p",
        ExpressionAttributeValues={":p": "BANS"},
    )
    return [Ban(**_from_item(i)) for i in items]


def ig_account_banned(username: str) -> bool:
    r = _table().get_item(Key={"PK": f"BANIG#{username.lower()}", "SK": "META"})
    return "Item" in r


# ----------------------------------------------------------------------- pay runs
def put_payrun(window: str, record: dict) -> None:
    body = json.loads(json.dumps(record, default=str), parse_float=Decimal)
    _table().put_item(Item={"PK": f"PAYRUN#{window}", "SK": "META", **body})


def get_payrun(window: str) -> dict | None:
    r = _table().get_item(Key={"PK": f"PAYRUN#{window}", "SK": "META"})
    return _from_item(r["Item"]) if "Item" in r else None
