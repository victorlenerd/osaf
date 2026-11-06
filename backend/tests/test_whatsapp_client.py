"""Replies leave from the business number the reviewer wrote to."""

import httpx
import pytest
import respx

from app.config import get_settings
from app.pipeline import runner
from app.whatsapp import client as wa

GRAPH = "https://graph.facebook.com"


@pytest.fixture
def configured():
    s = get_settings()
    before = (s.whatsapp_access_token, s.whatsapp_phone_number_id)
    s.whatsapp_access_token, s.whatsapp_phone_number_id = "tok", "999"
    yield s
    s.whatsapp_access_token, s.whatsapp_phone_number_id = before


def _url(sender: str) -> str:
    return f"{GRAPH}/{get_settings().graph_api_version}/{sender}/messages"


@respx.mock
def test_send_uses_configured_number_by_default(configured):
    route = respx.post(_url("999")).mock(return_value=httpx.Response(200, json={}))
    wa.send_text("2348012345678", "hi")
    assert route.called


@respx.mock
def test_send_and_mark_read_use_the_number_messaged(configured):
    live = respx.post(_url("1417")).mock(return_value=httpx.Response(200, json={}))
    default = respx.post(_url("999")).mock(return_value=httpx.Response(200, json={}))
    with wa.sending_from("1417"):
        wa.send_text("2348012345678", "hi")
        wa.mark_read("wamid.1")
    assert live.call_count == 2 and not default.called
    wa.send_text("2348012345678", "later")  # outside the block: back to the default
    assert default.call_count == 1


@respx.mock
@pytest.mark.parametrize("bad", [None, "", "12/../34", "abc", 1417])
def test_unusable_sender_id_falls_back(configured, bad):
    default = respx.post(_url("999")).mock(return_value=httpx.Response(200, json={}))
    with wa.sending_from(bad):
        wa.send_text("2348012345678", "hi")
    assert default.called


def test_process_inbound_replies_from_the_number_messaged(monkeypatch, configured):
    seen: list[str] = []
    monkeypatch.setattr(runner.wa, "send_text", lambda to, body, **k: seen.append(wa._sender_id()))

    def reply(phone, msg, name):
        runner.wa.send_text(phone, "hello")

    monkeypatch.setattr(runner, "_process_inbound", reply)
    runner.process_inbound("2348012345678", {}, "Ada", "1417")
    runner.process_inbound("2348012345678", {}, "Ada")
    assert seen == ["1417", "999"]


def test_error_reply_also_leaves_from_the_number_messaged(monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(runner.wa, "send_text", lambda to, body, **k: seen.append(wa._sender_id()))

    def boom(phone, msg, name):
        raise RuntimeError("x")

    monkeypatch.setattr(runner, "_process_inbound", boom)
    runner.process_inbound("2348012345678", {}, "Ada", "1417")
    assert seen == ["1417"]
