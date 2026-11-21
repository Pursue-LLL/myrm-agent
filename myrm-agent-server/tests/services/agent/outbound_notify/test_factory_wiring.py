"""Unit tests for append_channel_notify_tool factory wiring."""

from __future__ import annotations

from unittest.mock import patch

from app.services.agent.outbound_notify.factory_wiring import append_channel_notify_tool


def test_append_returns_zero_for_empty_targets() -> None:
    tools: list[object] = []
    assert append_channel_notify_tool((), tools) == 0
    assert tools == []


def test_append_returns_zero_when_sender_factory_returns_none() -> None:
    tools: list[object] = []
    with patch(
        "app.services.agent.outbound_notify.sender.create_notification_sender",
        return_value=None,
    ):
        count = append_channel_notify_tool(({"channel": "telegram", "recipient_id": "1"},), tools)
    assert count == 0
    assert tools == []


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


def test_append_accepts_allowed_roots_kwarg(tmp_path) -> None:
    tools: list[object] = []
    count = append_channel_notify_tool(
        ({"channel": "telegram", "recipient_id": "chat_1"},),
        tools,
        allowed_roots=(str(tmp_path),),
    )
    assert count == 1
    assert getattr(tools[0], "name", None) == "channel_notify_tool"


def test_append_respects_readonly_mode() -> None:
    tools: list[object] = []
    targets = ({"channel": "telegram", "recipient_id": "123", "label": "TG"},)

    # The read-only preset must not mount an outbound tool: it would be a data-egress path.
    assert append_channel_notify_tool(targets, tools, is_readonly=True) == 0
    assert tools == []

    assert append_channel_notify_tool(targets, tools, is_readonly=False) == 1
    assert [getattr(tool, "name", None) for tool in tools] == ["channel_notify_tool"]
