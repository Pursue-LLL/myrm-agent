"""Integration: factory wiring for channel_notify_tool (mirrors factory.py §4.5)."""

from __future__ import annotations

from app.services.agent.outbound_notify import (
    create_channel_notify_tool,
    create_notification_sender,
)


def _wire_notify_tool(
    notify_targets: tuple[dict[str, str], ...],
    deferred_tools: list[object],
) -> None:
    """Same logic as general_agent/factory.py channel notification block."""
    if notify_targets:
        sender_result = create_notification_sender(notify_targets)
        if sender_result:
            sender, notify_config = sender_result
            notify_tool = create_channel_notify_tool(sender, notify_config)
            deferred_tools.append(notify_tool)


def test_factory_registers_channel_notify_tool_when_targets_present() -> None:
    deferred_tools: list[object] = []
    targets = ({"channel": "telegram", "recipient_id": "chat_1", "label": "Alerts"},)

    _wire_notify_tool(targets, deferred_tools)

    assert len(deferred_tools) == 1
    assert getattr(deferred_tools[0], "name", None) == "channel_notify_tool"


def test_factory_skips_when_notify_targets_empty() -> None:
    deferred_tools: list[object] = []
    _wire_notify_tool((), deferred_tools)
    assert deferred_tools == []


def test_factory_tool_is_async_invokable() -> None:
    deferred_tools: list[object] = []
    _wire_notify_tool(({"channel": "slack", "recipient_id": "C1"},), deferred_tools)
    tool = deferred_tools[0]
    assert tool.coroutine is not None
