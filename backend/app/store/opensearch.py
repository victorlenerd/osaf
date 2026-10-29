"""Amazon OpenSearch: one `businesses` index, rebuilt per business on every publish."""

from __future__ import annotations

import logging
from functools import lru_cache

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
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
    creds = boto3.Session(region_name=s.aws_region).get_credentials()
    auth = AWS4Auth(
        creds.access_key, creds.secret_key, s.aws_region, "es", session_token=creds.token
    )
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
    if not client().indices.exists(index=idx):
        client().indices.create(index=idx, body=INDEX_BODY)
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


def search(
    q: str,
    *,
    country: str | None = None,
    category: str | None = None,
    limit: int = 20,
) -> list[dict]:
    filters = []
    if country:
        filters.append({"term": {"country": country.upper()}})
    if category:
        filters.append({"term": {"category": category}})
    if q.strip():
        must = {
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
    body = {
        "size": limit,
        "query": {
            "function_score": {
                "query": {"bool": {"must": must, "filter": filters}},
                "script_score": {
                    "script": {
                        "source": (
                            "_score * (1 + Math.log1p(doc['review_count'].value) "
                            "* (0.5 + doc['recommend_rate'].value))"
                        )
                    }
                },
                "boost_mode": "replace",
            }
        },
    }
    r = client().search(index=get_settings().opensearch_index, body=body)
    out = []
    for hit in r["hits"]["hits"]:
        src = hit["_source"]
        loc = src.get("location")
        out.append(
            {
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
        )
    return out
