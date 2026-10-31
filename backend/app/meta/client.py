"""Thin client for the Meta Model API (https://dev.meta.ai).

One Bearer key and one base URL cover the three models we use:
  * muse-spark-1.3          — chat completions with tool calling / JSON output (agent + summaries)
  * muse-voice-transcribe   — POST /v1/asr/transcribe (multipart WAV, diarization)
  * sam-3.1                 — POST /v1/responses with an input_video part (face detection/tracking)
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from openai import OpenAI

from app.config import get_settings

log = logging.getLogger(__name__)


class MetaClient:
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.openai = OpenAI(api_key=api_key, base_url=self.base_url, timeout=180, max_retries=2)

    # ---------------------------------------------------------------- Muse Spark
    def chat(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        response_format: dict | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        timeout: float | None = None,
    ) -> Any:
        kwargs: dict[str, Any] = {
            "model": model or get_settings().spark_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if timeout is not None:  # per-request override of the client's 180 s default
            kwargs["timeout"] = timeout
        if tools:
            kwargs["tools"] = tools
            if tool_choice:
                kwargs["tool_choice"] = tool_choice
        if response_format:
            kwargs["response_format"] = response_format
        return self.openai.chat.completions.create(**kwargs)

    # ------------------------------------------------------ Muse Voice Transcribe
    def transcribe(
        self,
        wav_path: Path,
        *,
        language_bias: list[str] | None = None,
        keywords: list[str] | None = None,
        mode: str = "DIARIZATION",
        session_id: str | None = None,
    ) -> dict:
        """File transcription. WAV must be mono 16-bit PCM at 16/24 kHz, <= 10 min, <= 32 MB."""
        req: dict[str, Any] = {
            "mode": mode,
            "model": get_settings().asr_model,
            "audioEncoding": "WAV",
        }
        if language_bias:
            req["languageBias"] = language_bias
        if keywords:
            req["keywords"] = keywords[:20]
        url = f"{self.base_url}/asr/transcribe"
        params = {"sessionId": session_id} if session_id else None
        with wav_path.open("rb") as f:
            files = {
                "request": (None, json.dumps(req), "application/json"),
                "audio": (wav_path.name, f, "audio/wav"),
            }
            r = httpx.post(
                url,
                params=params,
                headers={"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"},
                files=files,
                timeout=300,
            )
        if r.status_code >= 400:
            raise RuntimeError(f"ASR failed {r.status_code}: {r.text[:500]}")
        return r.json()

    # ------------------------------------------------------------------ SAM 3.1
    def sam_video_lines(
        self,
        video_url: str,
        prompt: str,
        *,
        include_confidence: bool = True,
    ) -> Iterator[str]:
        """Stream SAM 3.1 output for a video; yields one raw output_text line per frame.

        Each line starts with a frame marker like `<12f>` followed by comma-separated records
        `<id><|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..[;c=..]|><|mask;...|>`.
        """
        body: dict[str, Any] = {
            "model": get_settings().sam_model,
            "stream": True,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_video", "video_url": video_url},
                    ],
                }
            ],
        }
        # Options live under `metadata`; values are strings. one_bit masks are the smallest
        # encoding and we only need boxes, so keep the stream light.
        body["metadata"] = {"mask_encoding": "one_bit"}
        if include_confidence:
            body["metadata"]["include_confidence"] = "true"
        url = f"{self.base_url}/responses"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        buf = ""
        with httpx.stream("POST", url, headers=headers, json=body, timeout=600) as r:
            if r.status_code >= 400:
                r.read()
                raise RuntimeError(f"SAM failed {r.status_code}: {r.text[:500]}")
            for raw in r.iter_lines():
                if not raw.startswith("data:"):
                    continue
                data = raw[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    evt = json.loads(data)
                except json.JSONDecodeError:
                    continue
                etype = evt.get("type", "")
                if etype == "response.output_text.delta":
                    buf += evt.get("delta", "")
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        if line.strip():
                            yield line.strip()
                elif etype in ("response.completed", "response.incomplete"):
                    break
                elif etype in ("error", "response.failed"):
                    raise RuntimeError(f"SAM stream error: {json.dumps(evt)[:500]}")
        if buf.strip():
            yield buf.strip()


@lru_cache
def get_meta() -> MetaClient:
    s = get_settings()
    if not s.model_api_key:
        log.warning("MODEL_API_KEY is not set; Meta API calls will fail")
    return MetaClient(s.model_api_key, s.meta_api_base)
