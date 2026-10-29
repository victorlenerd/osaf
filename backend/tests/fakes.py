"""A scripted stand-in for MetaClient.chat used by the agent tests."""

from __future__ import annotations

import json
from types import SimpleNamespace


def tool_call(name: str, args: dict, call_id: str = "call_1"):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


def reply(content: str | None = None, tool_calls: list | None = None):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls or [])
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class ScriptedChat:
    """Returns the queued replies in order and records every call's messages."""

    def __init__(self, replies: list):
        self.replies = list(replies)
        self.calls: list[dict] = []

    def __call__(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        if not self.replies:
            raise AssertionError("ScriptedChat ran out of replies")
        return self.replies.pop(0)
