"""Fail-closed settings, keyed phone hashes, log redaction and download caps."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app import pii
from app.config import Settings, get_settings
from app.pipeline import download
from app.whatsapp import webhook

PROD_OK = dict(
    env="prod",
    model_api_key="k",
    meta_app_secret="s",
    whatsapp_access_token="t",
    whatsapp_phone_number_id="1",
    whatsapp_verify_token="a-long-enough-verify-token",
    phone_hash_salt="a-long-enough-random-salt",
)


def test_prod_requires_every_secret():
    assert Settings(_env_file=None, **PROD_OK).env == "prod"
    with pytest.raises(ValueError, match="META_APP_SECRET"):
        Settings(_env_file=None, **{**PROD_OK, "meta_app_secret": ""})
    with pytest.raises(ValueError, match="PHONE_HASH_SALT"):
        Settings(_env_file=None, **{**PROD_OK, "phone_hash_salt": "CHANGEME"})
    with pytest.raises(ValueError, match="WHATSAPP_VERIFY_TOKEN"):
        Settings(_env_file=None, **{**PROD_OK, "whatsapp_verify_token": "change-me"})
    with pytest.raises(ValueError, match="PHONE_HASH_SALT"):
        Settings(_env_file=None, **{**PROD_OK, "phone_hash_salt": "short"})


def test_dev_does_not_require_secrets():
    assert Settings(_env_file=None, env="dev").meta_app_secret == ""


def test_unsigned_webhook_only_accepted_in_dev(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "meta_app_secret", "")
    monkeypatch.setattr(s, "env", "dev")
    assert webhook._valid_signature(b"{}", None) is True
    monkeypatch.setattr(s, "env", "staging")
    assert webhook._valid_signature(b"{}", None) is False
    assert webhook._valid_signature(b"{}", "sha256=deadbeef") is False


def test_phone_hash_is_keyed(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "phone_hash_salt", "salt-one")
    a = pii.phone_hash("2348012345678")
    monkeypatch.setattr(s, "phone_hash_salt", "salt-two")
    b = pii.phone_hash("2348012345678")
    assert a != b and len(a) == 24
    assert "2348012345678" not in pii.phone_label("2348012345678")


def test_log_filter_masks_phone_numbers():
    f = pii.RedactPhoneNumbers()
    rec = logging.LogRecord(
        "t", logging.INFO, __file__, 1, "sent to %s id %s", ("2348012345678", "01HZX9"), None
    )
    assert f.filter(rec)
    assert rec.getMessage() == "sent to +*** id 01HZX9"
    rec = logging.LogRecord("t", logging.INFO, __file__, 1, "from +2348012345678 ok", None, None)
    f.filter(rec)
    assert rec.getMessage() == "from +*** ok"
    rec = logging.LogRecord(
        "t", logging.INFO, __file__, 1, "sub 01HZX9ABCDEF12345 price 12345", None, None
    )
    f.filter(rec)
    assert (
        rec.getMessage() == "sub 01HZX9ABCDEF12345 price 12345"
    )  # short numbers and ULIDs untouched


class _FakeYDL:
    """Stands in for yt_dlp.YoutubeDL: applies match_filter like the real thing, writes no file."""

    last_opts: dict = {}

    def __init__(self, opts):
        _FakeYDL.last_opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=True):
        info = {"duration": 1800, "title": "long"}
        if _FakeYDL.last_opts["match_filter"](info) is not None:
            return info  # skipped: yt-dlp downloads nothing
        raise AssertionError("should have been filtered")


def test_overlong_reel_is_refused_before_download(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(download.yt_dlp, "YoutubeDL", _FakeYDL)
    monkeypatch.setattr(get_settings(), "max_reel_seconds", 900)
    with pytest.raises(download.DownloadError) as e:
        download.download_reel("https://www.instagram.com/reel/abc/", tmp_path)
    assert "30 minutes" in str(e.value) and e.value.retryable_via_whatsapp is False
    assert _FakeYDL.last_opts["max_filesize"] == get_settings().max_reel_bytes
    assert _FakeYDL.last_opts["cachedir"] is False
