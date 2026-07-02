# outbound_notify/

## Overview

Server module for agent-initiated outbound channel notifications: types, whitelist
target resolution, session rate limits, ChannelGateway delivery, media attachments,
and optional `channel_notify_tool` LangChain adapter.

Agents wire via `app.ai_agents.general_agent.factory` →
`factory_wiring.append_channel_notify_tool` (Turn1 when `notify_targets` configured).

## Media Attachments

`channel_notify_tool` supports an optional `attachments` parameter accepting local
file paths or URLs. Attachments are converted to `MediaAttachment` objects (reusing
`app.channels.types.messages`) and delivered via the existing `OutboundMessage.media`
pipeline — all registered channel providers already handle `msg.media`.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `types.py` | Core | NotifyTarget, NotifyToolConfig, NotifyResult, NotifySessionState, system appendix | ✅ |
| `protocols.py` | Core | NotificationSender protocol (with media support) | ✅ |
| `target_resolver.py` | Core | resolve_notify_target whitelist resolution | ✅ |
| `sender.py` | Core | ChannelNotificationSender + create_notification_sender | ✅ |
| `factory_wiring.py` | Core | append_channel_notify_tool — GeneralAgent Turn1 wiring SSOT | ✅ |
| `channel_notify_tool.py` | Adapter | create_channel_notify_tool LangChain factory (with attachments) | ✅ |
| `__init__.py` | Package | Public exports | ✅ |

## Dependencies

- `app.channels` — ChannelGateway, OutboundMessage, MediaAttachment, guess_media_type
- `app.core.channel_bridge` — gateway singleton
