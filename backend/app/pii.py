"""Reviewer identity helpers: everything that leaves the request path (reviews, logs) uses a
keyed hash of the WhatsApp number, never the number itself."""

from __future__ import annotations

import hashlib
import hmac
import logging
import re

from app.config import get_settings

# A run of 10-15 digits with optional leading +: the shape of an E.164 number as WhatsApp sends it.
_PHONE_RE = re.compile(r"(?<![\w.])\+?\d{10,15}(?![\w.])")


def phone_hash(phone: str) -> str:
    """HMAC-SHA256 of the number under the deployment's secret salt, truncated to 24 hex chars."""
    salt = get_settings().phone_hash_salt or "dev-only-salt"
    return hmac.new(salt.encode(), phone.encode(), hashlib.sha256).hexdigest()[:24]


def phone_label(phone: str) -> str:
    """Short, stable identifier for log lines: the first 8 chars of the hash."""
    return "reviewer:" + phone_hash(phone)[:8]


def redact_phones(text: str) -> str:
    return _PHONE_RE.sub("+***", text)


class RedactPhoneNumbers(logging.Filter):
    """Mask anything that looks like a phone number in a log record and its arguments."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_phones(record.msg)
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(
                    redact_phones(a) if isinstance(a, str) else a for a in record.args
                )
            elif isinstance(record.args, dict):
                record.args = {
                    k: redact_phones(a) if isinstance(a, str) else a for k, a in record.args.items()
                }
        return True
