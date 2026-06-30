# outbound_notify/

## Overview

Server module for agent-initiated outbound channel notifications: types, whitelist
target resolution, session rate limits, ChannelGateway delivery, media attachments,
and optional `channel_notify_tool` LangChain adapter.

**Migration note:** Harness `toolkits/notification/` was removed. This server module
is the sole SSOT for channel notify tooling. Agents wire via
`app.ai_agents.general_agent.factory` → `create_channel_notify_tool`.

## Media Attachments

`channel_notify_tool` supports an optional `attachments` parameter accepting local
file paths or URLs. Attachments are converted to `MediaAttachment` objects (reusing
`app.channels.types.messages`) and delivered via the existing `OutboundMessage.media`
pipeline — all registered channel providers already handle `msg.media`.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `types.py` | Core | NotifyTarget, NotifyToolConfig, NotifyResult, NotifySessionState | ✅ |
| `protocols.py` | Core | NotificationSender protocol (with media support) | ✅ |
| `target_resolver.py` | Core | resolve_notify_target whitelist resolution | ✅ |
| `sender.py` | Core | ChannelNotificationSender + create_notification_sender | ✅ |
| `channel_notify_tool.py` | Adapter | create_channel_notify_tool LangChain factory (with attachments) | ✅ |
| `__init__.py` | Package | Public exports | ✅ |

## Dependencies

- `app.channels` — ChannelGateway, OutboundMessage, MediaAttachment, guess_media_type
- `app.core.channel_bridge` — gateway singleton
