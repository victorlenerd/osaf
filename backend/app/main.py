"""Afefehub backend entrypoint."""

from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.public import router as public_router
from app.config import get_settings
from app.whatsapp.webhook import router as whatsapp_router

settings = get_settings()
logging.basicConfig(
    level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("afefehub")

_VERIFY_TOKEN_RE = re.compile(r"(hub\.verify_token=)[^&\s\"]+")


class RedactVerifyToken(logging.Filter):
    """Keep the webhook verify token out of the uvicorn access log."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args and isinstance(record.args, tuple):
            record.args = tuple(
                _VERIFY_TOKEN_RE.sub(r"\1***", a) if isinstance(a, str) else a for a in record.args
            )
        record.msg = _VERIFY_TOKEN_RE.sub(r"\1***", str(record.msg))
        return True


logging.getLogger("uvicorn.access").addFilter(RedactVerifyToken())


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.opensearch_endpoint:
        try:
            from app.store.opensearch import ensure_index

            ensure_index()
        except Exception:  # noqa: BLE001
            log.exception("could not ensure OpenSearch index at startup")
    yield


app = FastAPI(title="Afefehub API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.public_site_url, "http://localhost:3000"],
    allow_origin_regex=r"https://[a-z0-9]+\.cloudfront\.net",  # pre-cutover site preview
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.include_router(whatsapp_router)
app.include_router(public_router)


@app.get("/healthz")
def healthz():
    return {"ok": True, "env": settings.env}
