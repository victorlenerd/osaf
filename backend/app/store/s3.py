"""S3 key layout and helpers. All artifacts for one submission live under submissions/<id>/."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import boto3

from app.config import get_settings


@lru_cache
def _client():
    return boto3.client("s3", region_name=get_settings().aws_region)


class Keys:
    @staticmethod
    def video(sid: str) -> str:
        return f"submissions/{sid}/source.mp4"

    @staticmethod
    def audio(sid: str) -> str:
        return f"submissions/{sid}/audio.wav"

    @staticmethod
    def voice_source(sid: str) -> str:
        return f"submissions/{sid}/voice.ogg"

    @staticmethod
    def voice_playback(sid: str) -> str:
        return f"submissions/{sid}/voice.m4a"

    @staticmethod
    def transcript_json(sid: str) -> str:
        return f"submissions/{sid}/transcript.json"

    @staticmethod
    def transcript_txt(sid: str) -> str:
        return f"submissions/{sid}/transcript.txt"

    @staticmethod
    def facecheck(sid: str, name: str) -> str:
        return f"submissions/{sid}/facecheck/{name}"

    @staticmethod
    def extraction(sid: str) -> str:
        return f"submissions/{sid}/extraction.json"

    @staticmethod
    def agent_trace(sid: str) -> str:
        return f"submissions/{sid}/agent_trace.jsonl"

    @staticmethod
    def summary_history(business_id: str, ts: str) -> str:
        safe = business_id.replace("/", "_")
        return f"businesses/{safe}/summary_history/{ts}.json"


def upload_file(path: Path, key: str, content_type: str | None = None) -> str:
    extra = {"ContentType": content_type} if content_type else {}
    _client().upload_file(str(path), get_settings().media_bucket, key, ExtraArgs=extra)
    return key


def put_json(obj, key: str) -> str:
    body = json.dumps(obj, ensure_ascii=False, indent=2, default=str).encode()
    _client().put_object(
        Bucket=get_settings().media_bucket, Key=key, Body=body, ContentType="application/json"
    )
    return key


def put_text(text: str, key: str) -> str:
    _client().put_object(
        Bucket=get_settings().media_bucket,
        Key=key,
        Body=text.encode(),
        ContentType="text/plain; charset=utf-8",
    )
    return key


def append_jsonl(line: dict, key: str) -> None:
    """Append-by-rewrite; traces are small and this keeps the layout simple."""
    s = get_settings()
    try:
        existing = _client().get_object(Bucket=s.media_bucket, Key=key)["Body"].read().decode()
    except _client().exceptions.NoSuchKey:
        existing = ""
    existing += json.dumps(line, ensure_ascii=False, default=str) + "\n"
    _client().put_object(
        Bucket=s.media_bucket, Key=key, Body=existing.encode(), ContentType="application/x-ndjson"
    )


def get_json(key: str):
    body = _client().get_object(Bucket=get_settings().media_bucket, Key=key)["Body"].read()
    return json.loads(body)


def download_file(key: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _client().download_file(get_settings().media_bucket, key, str(path))
    return path


def presigned_url(key: str, expires: int = 3600) -> str:
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": get_settings().media_bucket, "Key": key},
        ExpiresIn=expires,
    )
