"""Integration: factory wiring for channel_notify_tool (mirrors factory.py §4.5)."""

from __future__ import annotations

from app.services.agent.outbound_notify.factory_wiring import append_channel_notify_tool


def test_factory_registers_channel_notify_tool_when_targets_present() -> None:
    tools: list[object] = []
    targets = ({"channel": "telegram", "recipient_id": "chat_1", "label": "Alerts"},)

    target_count = append_channel_notify_tool(targets, tools)

    assert target_count == 1
    assert len(tools) == 1
    assert getattr(tools[0], "name", None) == "channel_notify_tool"


def test_factory_skips_when_notify_targets_empty() -> None:
    tools: list[object] = []
    assert append_channel_notify_tool((), tools) == 0
    assert tools == []


def test_factory_tool_is_async_invokable() -> None:
    tools: list[object] = []
    append_channel_notify_tool(({"channel": "slack", "recipient_id": "C1"},), tools)
    tool = tools[0]
    assert tool.coroutine is not None
