"""Unit tests for append_channel_notify_tool factory wiring."""

from __future__ import annotations

from app.services.agent.outbound_notify.factory_wiring import append_channel_notify_tool


def test_append_returns_allowed_target_count() -> None:
    tools: list[object] = []
    count = append_channel_notify_tool(
        (
            {"channel": "telegram", "recipient_id": "chat_1", "label": "Primary"},
            {"channel": "slack", "recipient_id": "C1"},
        ),
        tools,
    )
    assert count == 2
    assert getattr(tools[0], "name", None) == "channel_notify_tool"
