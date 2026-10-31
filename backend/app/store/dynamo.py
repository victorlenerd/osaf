"""Single-table DynamoDB access.

PK / SK layout
  CONV#<phone>        META                       Conversation
  CONV#<phone>        POINTS                     reviewer reward balance {points, updated_at}
  SUB#<id>            META                       Submission   GSI1: CONV#<phone>/SUB#<created>
  WAMSG#<wamid>       META                       webhook dedupe (TTL 24h)
  REEL#<shortcode>    META                       one review per reel
  BIZ#<id>            META                       Business     GSI1: CAT#<category>/BIZ#<updated>
  BIZ#<id>            REV#<created_at>#<rid>     Review       GSI1: REVIEWER#<hash>/REV#<created>
  REVIEW#<rid>        META                       pointer {business_id, sk} for lookup by id
  BIZ#<id>            SUMMARY                    BusinessSummary
  GPLACE#<place_id>   SUMMARY                    GoogleReviewSummary (TTL; raw Google reviews
                                                 are never stored)
"""

from __future__ import annotations

import json
import time
from decimal import Decimal
from functools import lru_cache
from typing import Any

import boto3
from botocore.exceptions import ClientError
from pydantic import BaseModel

from app.config import get_settings
from app.models import (
    Business,
    BusinessSummary,
    Conversation,
    GoogleReviewSummary,
    Review,
    ReviewExtraction,
    Submission,
    now_iso,
)


@lru_cache
def _table():
    s = get_settings()
    return boto3.resource("dynamodb", region_name=s.aws_region).Table(s.dynamo_table)


def _to_item(model: BaseModel) -> dict:
    return json.loads(model.model_dump_json(exclude_none=True), parse_float=Decimal)


def _from_item(item: dict) -> dict:
    def conv(v: Any):
        if isinstance(v, Decimal):
            return int(v) if v == v.to_integral_value() else float(v)
        if isinstance(v, dict):
            return {k: conv(x) for k, x in v.items()}
        if isinstance(v, list):
            return [conv(x) for x in v]
        return v

    return {k: conv(v) for k, v in item.items() if k not in {"PK", "SK", "GSI1PK", "GSI1SK"}}


# ------------------------------------------------------------------ conversations
def get_conversation(phone: str) -> Conversation | None:
    r = _table().get_item(Key={"PK": f"CONV#{phone}", "SK": "META"})
    return Conversation(**_from_item(r["Item"])) if "Item" in r else None


def put_conversation(c: Conversation) -> None:
    c.updated_at = now_iso()
    _table().put_item(Item={"PK": f"CONV#{c.phone}", "SK": "META", **_to_item(c)})


# -------------------------------------------------------------------- submissions
def get_submission(sid: str) -> Submission | None:
    r = _table().get_item(Key={"PK": f"SUB#{sid}", "SK": "META"})
    return Submission(**_from_item(r["Item"])) if "Item" in r else None


def put_submission(s: Submission) -> None:
    if s.expires_at is None:
        s.expires_at = int(time.time()) + 7 * 86400
    _table().put_item(
        Item={
            "PK": f"SUB#{s.submission_id}",
            "SK": "META",
            "GSI1PK": f"CONV#{s.phone}",
            "GSI1SK": f"SUB#{s.created_at}",
            **_to_item(s),
        }
    )


def list_submissions_for_phone(phone: str, limit: int = 20) -> list[Submission]:
    r = _table().query(
        IndexName="GSI1",
        KeyConditionExpression="GSI1PK = :p AND begins_with(GSI1SK, :s)",
        ExpressionAttributeValues={":p": f"CONV#{phone}", ":s": "SUB#"},
        ScanIndexForward=False,
        Limit=limit,
    )
    return [Submission(**_from_item(i)) for i in r.get("Items", [])]


# -------------------------------------------------------------- idempotency locks
def _claim(pk: str, ttl_seconds: int, extra: dict | None = None) -> bool:
    try:
        _table().put_item(
            Item={
                "PK": pk,
                "SK": "META",
                "created_at": now_iso(),
                "expires_at": int(time.time()) + ttl_seconds,
                **(extra or {}),
            },
            ConditionExpression="attribute_not_exists(PK)",
        )
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def claim_wa_message(wamid: str) -> bool:
    """True the first time a WhatsApp message id is seen (webhooks are retried/duplicated)."""
    return _claim(f"WAMSG#{wamid}", 86400)


def claim_reel(shortcode: str, review_id: str) -> bool:
    """One published review per reel. No TTL (set far future so the attribute exists)."""
    return _claim(f"REEL#{shortcode}", 10 * 365 * 86400, {"review_id": review_id})


# ---------------------------------------------------------------------- business
def get_business(business_id: str) -> Business | None:
    r = _table().get_item(Key={"PK": f"BIZ#{business_id}", "SK": "META"})
    return Business(**_from_item(r["Item"])) if "Item" in r else None


def upsert_business_on_publish(ext: ReviewExtraction) -> Business:
    """Atomic upsert: counters ADD, identity fields only set when missing."""
    b = ext.business
    now = now_iso()
    names: dict[str, Any] = {
        ":now": now,
        ":name": b.name,
        ":addr": b.formatted_address,
        ":country": b.country,
        ":city": b.city or "",
        ":lat": Decimal(str(b.lat)) if b.lat is not None else Decimal(0),
        ":lng": Decimal(str(b.lng)) if b.lng is not None else Decimal(0),
        ":cat": ext.category,
        ":ptype": b.primary_type or "",
        ":source": b.source,
        ":bid": b.place_id,
        ":zero": 0,
        ":gsi1pk": f"CAT#{ext.category}",
        ":gsi1sk": f"BIZ#{now}",
        ":said": [ext.business_name_as_said] if ext.business_name_as_said else [],
        ":empty_list": [],
        ":empty_map": {},
    }
    set_parts = [
        "business_id = if_not_exists(business_id, :bid)",
        "#src = if_not_exists(#src, :source)",
        "#name = if_not_exists(#name, :name)",
        "formatted_address = if_not_exists(formatted_address, :addr)",
        "country = if_not_exists(country, :country)",
        "city = if_not_exists(city, :city)",
        "lat = if_not_exists(lat, :lat)",
        "lng = if_not_exists(lng, :lng)",
        "category = if_not_exists(category, :cat)",
        "google_primary_type = if_not_exists(google_primary_type, :ptype)",
        "created_at = if_not_exists(created_at, :now)",
        "updated_at = :now",
        "GSI1PK = :gsi1pk",
        "GSI1SK = :gsi1sk",
        "names_as_said = list_append(if_not_exists(names_as_said, :empty_list), :said)",
        "keywords = if_not_exists(keywords, :empty_map)",
        "recommend_counts = if_not_exists(recommend_counts, :empty_map)",
        "review_count = if_not_exists(review_count, :zero)",
    ]
    _table().update_item(
        Key={"PK": f"BIZ#{b.place_id}", "SK": "META"},
        UpdateExpression="SET " + ", ".join(set_parts),
        ExpressionAttributeNames={"#src": "source", "#name": "name"},
        ExpressionAttributeValues=names,
    )
    # Second call: nested counters (ADD on nested map paths needs the maps to exist first).
    add_names = {"#rc": "recommend_counts", "#r": ext.recommend, "#kw": "keywords"}
    add_parts = ["review_count :one", "#rc.#r :one"]
    vals: dict[str, Any] = {":one": 1}
    for i, kw in enumerate(dict.fromkeys(k.strip().lower() for k in ext.keywords if k.strip())):
        add_names[f"#k{i}"] = kw
        add_parts.append(f"#kw.#k{i} :one")
    _table().update_item(
        Key={"PK": f"BIZ#{b.place_id}", "SK": "META"},
        UpdateExpression="ADD " + ", ".join(add_parts),
        ExpressionAttributeNames=add_names,
        ExpressionAttributeValues=vals,
    )
    biz = get_business(b.place_id)
    assert biz is not None
    return biz


def list_businesses_by_category(category: str, limit: int = 50) -> list[Business]:
    r = _table().query(
        IndexName="GSI1",
        KeyConditionExpression="GSI1PK = :p",
        ExpressionAttributeValues={":p": f"CAT#{category}"},
        ScanIndexForward=False,
        Limit=limit,
    )
    return [Business(**_from_item(i)) for i in r.get("Items", [])]


# ----------------------------------------------------------------------- reviews
def put_review(r: Review) -> None:
    sk = f"REV#{r.created_at}#{r.review_id}"
    _table().put_item(
        Item={
            "PK": f"BIZ#{r.business_id}",
            "SK": sk,
            "GSI1PK": f"REVIEWER#{r.reviewer_phone_hash}",
            "GSI1SK": f"REV#{r.created_at}",
            **_to_item(r),
        }
    )
    # Reviews are keyed by business; this pointer lets the audio endpoint find one by id.
    _table().put_item(
        Item={"PK": f"REVIEW#{r.review_id}", "SK": "META", "business_id": r.business_id, "sk": sk}
    )


def get_review(review_id: str) -> Review | None:
    ptr = _table().get_item(Key={"PK": f"REVIEW#{review_id}", "SK": "META"}).get("Item")
    if not ptr:
        return None
    r = _table().get_item(Key={"PK": f"BIZ#{ptr['business_id']}", "SK": ptr["sk"]})
    return Review(**_from_item(r["Item"])) if "Item" in r else None


def list_reviews(business_id: str, limit: int = 100) -> list[Review]:
    r = _table().query(
        KeyConditionExpression="PK = :p AND begins_with(SK, :s)",
        ExpressionAttributeValues={":p": f"BIZ#{business_id}", ":s": "REV#"},
        ScanIndexForward=False,
        Limit=limit,
    )
    return [Review(**_from_item(i)) for i in r.get("Items", [])]


def list_reviews_by_reviewer_since(
    reviewer_hash: str, since_iso: str, limit: int = 50
) -> list[Review]:
    """Reviews one person published at or after `since_iso`, oldest first."""
    r = _table().query(
        IndexName="GSI1",
        KeyConditionExpression="GSI1PK = :p AND GSI1SK >= :s",
        ExpressionAttributeValues={":p": f"REVIEWER#{reviewer_hash}", ":s": f"REV#{since_iso}"},
        ScanIndexForward=True,
        Limit=limit,
    )
    return [Review(**_from_item(i)) for i in r.get("Items", [])]


# ------------------------------------------------------------------------ points
def add_points(phone: str, n: int) -> int:
    """Atomically add `n` to a reviewer's balance (own item, so no read-modify-write race)."""
    r = _table().update_item(
        Key={"PK": f"CONV#{phone}", "SK": "POINTS"},
        UpdateExpression="ADD points :n SET updated_at = :now",
        ExpressionAttributeValues={":n": n, ":now": now_iso()},
        ReturnValues="UPDATED_NEW",
    )
    return int(r["Attributes"]["points"])


def get_points(phone: str) -> int:
    r = _table().get_item(Key={"PK": f"CONV#{phone}", "SK": "POINTS"})
    return int(r["Item"].get("points", 0)) if "Item" in r else 0


# ----------------------------------------------------------------------- summary
def get_summary(business_id: str) -> BusinessSummary | None:
    r = _table().get_item(Key={"PK": f"BIZ#{business_id}", "SK": "SUMMARY"})
    return BusinessSummary(**_from_item(r["Item"])) if "Item" in r else None


def put_summary(business_id: str, s: BusinessSummary) -> None:
    _table().put_item(Item={"PK": f"BIZ#{business_id}", "SK": "SUMMARY", **_to_item(s)})


# --------------------------------------------------- Google reviews summary cache
def get_google_summary(place_id: str) -> GoogleReviewSummary | None:
    """Cached summary, or None when missing or past its TTL (Dynamo deletes lazily, up to 48 h)."""
    r = _table().get_item(Key={"PK": f"GPLACE#{place_id}", "SK": "SUMMARY"})
    if "Item" not in r:
        return None
    s = GoogleReviewSummary(**_from_item(r["Item"]))
    if s.expires_at is None or s.expires_at <= int(time.time()):
        return None
    return s


def put_google_summary(place_id: str, s: GoogleReviewSummary) -> None:
    if s.expires_at is None:
        s.expires_at = int(time.time()) + get_settings().google_summary_ttl_seconds
    _table().put_item(Item={"PK": f"GPLACE#{place_id}", "SK": "SUMMARY", **_to_item(s)})


# ------------------------------------------------------------------- maintenance
def delete_business(business_id: str) -> int:
    """Remove a business and everything under its partition (reviews, summary). Returns count."""
    pk = f"BIZ#{business_id}"
    n = 0
    start = None
    with _table().batch_writer() as batch:
        while True:
            kwargs: dict[str, Any] = {
                "KeyConditionExpression": "PK = :p",
                "ExpressionAttributeValues": {":p": pk},
                "ProjectionExpression": "PK, SK",
            }
            if start:
                kwargs["ExclusiveStartKey"] = start
            r = _table().query(**kwargs)
            for item in r.get("Items", []):
                batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
                n += 1
            start = r.get("LastEvaluatedKey")
            if not start:
                break
    return n
