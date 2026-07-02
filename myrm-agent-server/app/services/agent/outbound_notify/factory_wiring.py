"""GeneralAgent factory wiring for channel_notify_tool.

[INPUT]
- .sender::create_notification_sender (POS: build sender from notify_targets)
- .channel_notify_tool::create_channel_notify_tool (POS: LangChain adapter factory)

[OUTPUT]
- append_channel_notify_tool(): Append tool to Turn1 tools when targets exist; returns allowed target count (0 = not loaded).

[POS]
Single SSOT for factory.py and integration tests — avoids duplicated wiring logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool


def append_channel_notify_tool(
    notify_targets: tuple[dict[str, str], ...],
    tools: list[BaseTool],
) -> int:
    """Append channel_notify_tool when notify_targets are configured.

    Returns the number of allowed targets when the tool was appended, else 0.
    """
    if not notify_targets:
        return 0

    from .channel_notify_tool import create_channel_notify_tool
    from .sender import create_notification_sender

    sender_result = create_notification_sender(notify_targets)
    if sender_result is None:
        return 0

    sender, notify_config = sender_result
    tools.append(create_channel_notify_tool(sender, notify_config))
    return len(notify_config.allowed_targets)
