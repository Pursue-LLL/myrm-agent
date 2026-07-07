# outbound_notify/

## Overview

Server module for agent-initiated outbound channel notifications: types, whitelist
target resolution, session rate limits, ChannelGateway delivery, media attachments,
and optional `channel_notify_tool` LangChain adapter.

Agents wire via `app.ai_agents.general_agent.factory` →
`factory_wiring.append_channel_notify_tool` (Turn1 when `notify_targets` configured).
Delivery uses `ChannelGateway.bus.send_tracked` (synchronous success/failure).
On send failure after retries, `MessageBus._record_outbound_failure` writes DLQ and invokes
`channel_bridge.handle_dead_letter` via `on_permanent_failure` (SSE + system notification).
Persistent dedupe via `SqliteDeliveryNotifyLedger` (`state_dir/delivery_notify_ledger.db`) prevents
duplicate toasts after restart. Agent notify failures set `suppress_im_notification` on the event so
`NotificationDispatcher` does not IM-alert the same failed channel.
Sync-path (`send_tracked`) failures mark the delivery id on the DLQ instance to prevent a
second callback when the DLQ retry loop runs.

Subagents cannot inherit `channel_notify_tool`: server bootstrap registers it via
`register_leaf_blocked_tools` (`_tool_layer_bootstrap.py`).

Frontend recipient picker uses `GET /channels/manage/status` (running channels) and
`GET /channels/manage/pairings`.

**Test coverage**: 48 server (outbound_notify module) + 7 frontend vitest; full notify+DLQ chain 106+ with `test_bus.py`.

## Media Attachments

`channel_notify_tool` supports an optional `attachments` parameter accepting local
file paths or URLs. Local paths must resolve under the agent's `declared_allowed_roots`
(see `attachment_path_policy.py`). Attachments are converted to `MediaAttachment` objects (reusing
`app.channels.types.messages`) and delivered via the existing `OutboundMessage.media`
pipeline — all registered channel providers already handle `msg.media`.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `types.py` | Core | NotifyTarget, NotifyToolConfig, NotifyResult, NotifySessionState, system appendix | ✅ |
| `protocols.py` | Core | NotificationSender protocol (with media support) | ✅ |
| `target_resolver.py` | Core | resolve_notify_target whitelist resolution | ✅ |
| `sender.py` | Core | ChannelNotificationSender + create_notification_sender; uses `bus.send_tracked` for reliable delivery | ✅ |
| `factory_wiring.py` | Core | append_channel_notify_tool — GeneralAgent Turn1 wiring SSOT | ✅ |
| `attachment_path_policy.py` | Core | Local attachment path guard (agent allowed_roots) | ✅ |
| `channel_notify_tool.py` | Adapter | create_channel_notify_tool LangChain factory (with attachments) | ✅ |
| `__init__.py` | Package | Public exports | ✅ |

## Dependencies

- `app.channels` — ChannelGateway, OutboundMessage, MediaAttachment, guess_media_type
- `app.core.channel_bridge` — gateway singleton
