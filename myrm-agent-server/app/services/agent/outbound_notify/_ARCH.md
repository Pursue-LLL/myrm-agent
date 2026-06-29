# outbound_notify/

## Overview

Server module for agent-initiated outbound channel notifications: types, whitelist
target resolution, session rate limits, ChannelGateway delivery, and optional
`channel_notify_tool` LangChain adapter.

**Migration note:** Harness `toolkits/notification/` was removed; this server module
is the sole SSOT for channel notify tooling. Wire agents via
`app.ai_agents.general_agent.factory` → `create_channel_notify_tool`.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `types.py` | Core | NotifyTarget, NotifyToolConfig, NotifyResult, NotifySessionState | ✅ |
| `protocols.py` | Core | NotificationSender protocol | ✅ |
| `target_resolver.py` | Core | resolve_notify_target whitelist resolution | ✅ |
| `sender.py` | Core | ChannelNotificationSender + create_notification_sender | ✅ |
| `channel_notify_tool.py` | Adapter | create_channel_notify_tool LangChain factory | ✅ |
| `__init__.py` | Package | Public exports | ✅ |

## Dependencies

- `app.channels` — ChannelGateway, OutboundMessage
- `app.core.channel_bridge` — gateway singleton
