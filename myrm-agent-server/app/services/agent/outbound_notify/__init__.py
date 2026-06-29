"""Agent-initiated outbound channel notifications.

[INPUT]
- outbound_notify.protocols::NotificationSender (POS: outbound notification sender protocol)
- outbound_notify.sender::ChannelNotificationSender (POS: ChannelGateway delivery)
- outbound_notify.channel_notify_tool::create_channel_notify_tool (POS: LangChain adapter)

[OUTPUT]
- Public API: types, sender, target resolver, optional LangChain tool factory.

[POS]
Server module for agent-initiated outbound channel notifications.
"""

from .channel_notify_tool import create_channel_notify_tool
from .protocols import NotificationSender
from .sender import ChannelNotificationSender, create_notification_sender
from .target_resolver import resolve_notify_target
from .types import NotifyResult, NotifySessionState, NotifyTarget, NotifyToolConfig

__all__ = [
    "ChannelNotificationSender",
    "NotificationSender",
    "NotifyResult",
    "NotifySessionState",
    "NotifyTarget",
    "NotifyToolConfig",
    "create_channel_notify_tool",
    "create_notification_sender",
    "resolve_notify_target",
]
