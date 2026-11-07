"""Amazon OpenSearch: one `businesses` index, rebuilt per business on every publish."""

from __future__ import annotations

import logging
import math
from functools import lru_cache

import boto3
from opensearchpy import OpenSearch, RequestError, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

from app.config import get_settings
from app.models import Business, BusinessSummary

log = logging.getLogger(__name__)

INDEX_BODY = {
    "settings": {
        "index": {"number_of_shards": 1, "number_of_replicas": 0},
        "analysis": {
            "filter": {"edge_2_15": {"type": "edge_ngram", "min_gram": 2, "max_gram": 15}},
            "analyzer": {
                "name_index": {
                    "tokenizer": "standard",
                    "filter": ["lowercase", "asciifolding", "edge_2_15"],
                },
                "name_search": {"tokenizer": "standard", "filter": ["lowercase", "asciifolding"]},
            },
        },
    },
    "mappings": {
        "properties": {
            "business_id": {"type": "keyword"},
            "name": {
                "type": "text",
                "analyzer": "name_index",
                "search_analyzer": "name_search",
                "fields": {"raw": {"type": "keyword"}},
            },
            "names_as_said": {
                "type": "text",
                "analyzer": "name_index",
                "search_analyzer": "name_search",
            },
            "formatted_address": {"type": "text", "analyzer": "name_search"},
            "city": {"type": "keyword", "fields": {"text": {"type": "text"}}},
            "country": {"type": "keyword"},
            "category": {"type": "keyword"},
            "source": {"type": "keyword"},
            "keywords": {
                "type": "text",
                "analyzer": "name_search",
                "fields": {"raw": {"type": "keyword"}},
            },
            "summary_headline": {"type": "text"},
            "praise": {"type": "text"},
            "complaints": {"type": "text"},
            "location": {"type": "geo_point"},
            "review_count": {"type": "integer"},
            "recommend_rate": {"type": "float"},
            "overall_sentiment": {"type": "keyword"},
            "updated_at": {"type": "date"},
        }
    },
}


@lru_cache
def client() -> OpenSearch:
    s = get_settings()
    # The client is cached for the life of the process, so the signer must read the
    # credentials object on every request: on Fargate the task role's temporary token
    # rotates, and a copy of the key/secret/token taken at startup expires within hours.
    creds = boto3.Session(region_name=s.aws_region).get_credentials()
    auth = AWS4Auth(refreshable_credentials=creds, region=s.aws_region, service="es")
    return OpenSearch(
        hosts=[{"host": s.opensearch_endpoint, "port": 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=20,
    )


def ensure_index() -> None:
    idx = get_settings().opensearch_index
    if client().indices.exists(index=idx):
        return
    try:
        client().indices.create(index=idx, body=INDEX_BODY)
    except RequestError as e:  # several uvicorn workers race to create it at startup
        if e.error != "resource_already_exists_exception":
            raise
        return
    log.info("created index %s", idx)


def business_doc(b: Business, summary: BusinessSummary | None) -> dict:
    top_keywords = [k for k, _ in sorted(b.keywords.items(), key=lambda kv: -kv[1])[:20]]
    doc = {
        "business_id": b.business_id,
        "name": b.name,
        "names_as_said": sorted(set(b.names_as_said)),
        "formatted_address": b.formatted_address,
        "city": b.city,
        "country": b.country,
        "category": b.category,
        "source": b.source,
        "keywords": top_keywords,
        "summary_headline": summary.headline if summary else None,
        "praise": " ".join(summary.recurring_praise) if summary else None,
        "complaints": " ".join(summary.recurring_complaints) if summary else None,
        "review_count": b.review_count,
        "recommend_rate": round(b.recommend_rate, 3),
        "overall_sentiment": summary.overall_sentiment if summary else None,
        "updated_at": b.updated_at,
    }
    if b.lat and b.lng:
        doc["location"] = {"lat": b.lat, "lon": b.lng}
    return doc


def upsert_business(b: Business, summary: BusinessSummary | None) -> None:
    client().index(
        index=get_settings().opensearch_index,
        id=b.business_id,
        body=business_doc(b, summary),
        refresh=True,
    )


def delete_business(business_id: str) -> None:
    client().delete(
        index=get_settings().opensearch_index, id=business_id, ignore=[404], refresh=True
    )


RANK_SCRIPT = {
    "script_score": {
        "script": {
            "source": (
                "_score * (1 + Math.log1p(doc['review_count'].value) "
                "* (0.5 + doc['recommend_rate'].value))"
            )
        }
    }
}


def build_search_body(
    q: str,
    *,
    country: str | None = None,
    category: str | None = None,
    city: str | None = None,
    near: tuple[float, float, float] | None = None,
    exclude_ids: list[str] | None = None,
    limit: int = 20,
) -> dict:
    """The query for `search`. `city` is a city or an area ("Lekki", "Wuse 2"): it matches the
    city field or the address. `near` is (lat, lng, radius_km): only businesses inside the
    radius, closer ones ranked higher."""
    filters: list[dict] = []
    if country:
        filters.append({"term": {"country": country.upper()}})
    if category:
        filters.append({"term": {"category": category}})
    if city and city.strip():
        filters.append(
            {
                "bool": {
                    "should": [
                        {"term": {"city": city.strip()}},
                        {"match": {"city.text": {"query": city, "operator": "and"}}},
                        {"match": {"formatted_address": {"query": city, "operator": "and"}}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )
    if near:
        lat, lng, radius_km = near
        filters.append(
            {"geo_distance": {"distance": f"{radius_km}km", "location": {"lat": lat, "lon": lng}}}
        )
    if q.strip():
        must: dict = {
            "multi_match": {
                "query": q,
                "type": "best_fields",
                "fuzziness": "AUTO",
                "fields": [
                    "name^4",
                    "names_as_said^3",
                    "keywords^2",
                    "formatted_address",
                    "city.text",
                    "summary_headline",
                    "praise",
                ],
            }
        }
    else:
        must = {"match_all": {}}
    query: dict = {"bool": {"must": must, "filter": filters}}
    if exclude_ids:
        query["bool"]["must_not"] = [{"ids": {"values": list(exclude_ids)}}]
    functions: list[dict] = [RANK_SCRIPT]
    if near:
        lat, lng, radius_km = near
        functions.append(
            {
                "gauss": {
                    "location": {
                        "origin": {"lat": lat, "lon": lng},
                        "scale": f"{max(radius_km / 2, 0.5)}km",
                    }
                }
            }
        )
    return {
        "size": limit,
        "query": {
            "function_score": {
                "query": query,
                "functions": functions,
                "score_mode": "multiply",
                "boost_mode": "replace",
            }
        },
    }


def _distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def search(
    q: str,
    *,
    country: str | None = None,
    category: str | None = None,
    city: str | None = None,
    near: tuple[float, float, float] | None = None,
    exclude_ids: list[str] | None = None,
    limit: int = 20,
) -> list[dict]:
    body = build_search_body(
        q,
        country=country,
        category=category,
        city=city,
        near=near,
        exclude_ids=exclude_ids,
        limit=limit,
    )
    r = client().search(index=get_settings().opensearch_index, body=body)
    out = []
    for hit in r["hits"]["hits"]:
        src = hit["_source"]
        loc = src.get("location")
        row = {
            "business_id": src["business_id"],
            "name": src["name"],
            "formatted_address": src.get("formatted_address", ""),
            "city": src.get("city"),
            "country": src.get("country"),
            "category": src.get("category"),
            "review_count": src.get("review_count", 0),
            "recommend_rate": src.get("recommend_rate", 0.0),
            "overall_sentiment": src.get("overall_sentiment"),
            "summary_headline": src.get("summary_headline"),
            "location": {"lat": loc["lat"], "lng": loc["lon"]} if loc else None,
            "score": hit.get("_score"),
        }
        if near and loc:
            row["distance_km"] = round(_distance_km(near[0], near[1], loc["lat"], loc["lon"]), 1)
        out.append(row)
    return out
