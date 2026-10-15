# Notifications Module Architecture

## Purpose

Event-driven IM notification dispatch. Subscribes to the global `ServerEventBus`
and pushes human-readable notifications to user-configured IM channels
(multi-channel) via `ChannelGateway.publish()`.

边界约束：
- 本模块只负责“消息投递”，不是审批事实源
- `Review Inbox` 的真实待审数据来自 Harness 审批队列（`pending_records`）、记忆冲突待裁决行（`PendingMemory`）、审批主链上的 evolution records，以及 migration pending records
- 如需提醒用户有待审项，可以复用通知模块发送提醒，但不能把通知记录当成审批状态来源

## Data Flow

```
 pairing_store / approvals / health / budget / skills / channels / ...
       ↓ publish(AppEvent)
    ServerEventBus (fan-out)
     ↓               ↓                       ↓
  SSE (Web)    NotificationDispatcher (IM)    WebPushDispatcher (Web Push)
                      ↓ format_notification()      ↓ pywebpush + VAPID
                        (per target channel)
               ChannelGateway.publish()       Push Service (FCM/APNS/Mozilla)
                      ↓                            ↓
               WhatsApp / Telegram / ...     Browser Service Worker → OS notification
```

### Supported Event Templates

| AppEventType | IM Push | Trigger Source |
|---|---|---|
| `PAIRING_PENDING` | ✅ | `pairing_store` |
| `APPROVAL_REQUIRED` | ✅ | `approvals/registry` |
| `HEALTH_ALERT` | ✅ | `health/router` + `health_alert_policy` (fail-only: AgentEngine/Database/Network/VectorDB/DLQ; never SystemResources) |
| `BUDGET_ALERT` | ✅ | `budget/enforcer` |
| `NEW_SKILL_DRAFT` | ✅ | `skills/draft_notification` |
| `MESSAGE_DEAD_LETTERED` | ✅ | `channels/__init__` |
| `CHANNEL_DISCONNECTED` | ✅ | `core/channel_bridge/setup` |
| `WECHAT_SESSION_EXPIRED` | ✅ | (reserved) |
| `CONFIG_HEALTH_WARNING` | ✅ | (reserved) |
| `SYSTEM_NOTIFICATION` | ✅ | `background_job_finish_handler`, `skills/nightly_review`, `checkpoint/*`, `cron/push_store`, `goals/goal_stream_trigger`, `channel_bridge/webui_voice_work_notifier` (idle-task completions never raise one) |
| `KANBAN_TASK_UPDATED` | ✅ (terminal only) | `services/kanban/service` — completed/blocked/failed actions trigger IM push; lifecycle events silently skipped |
| `GOAL_TERMINAL` | ✅ | `ai_agents/general_agent/goal_learnings` — pushed when a Goal reaches terminal state (complete/cancelled/budget_limited/needs_human_review); IM message includes files_modified, turns_used, execution_duration_s, total_tokens, total_cost_usd and verifications. Additionally, `GoalTerminalNotifier` (in `channel_bridge/goal_terminal_notifier.py`) delivers results back to the originating IM thread when the Goal carries source channel metadata |
| `OAUTH_REAUTH_REQUIRED` | ✅ | `services/agent/oauth_refresher` — published when the provider rejects the refresh grant (HTTP 400/401 with an OAuth error body), or the refresh_token is missing; per-issuer 300s dedup to avoid notification storms |

Events not in `_EVENT_TEMPLATES` (e.g. `IDLE_STATUS`)
are silently skipped — they are high-frequency or internal and not suitable for IM push.

## Files

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Facade | Module public facade — exports NotificationDispatcher, FormattedNotification, format_notification | ✅ |
| `dispatcher.py` | Core | `NotificationDispatcher` — subscribes to ServerEventBus, formats one card per configured target (channel-aware; the owner's language is resolved once per event, only for `LOCALIZED_EVENT_TYPES`) and sends it via Gateway | ✅ |
| `adaptive_cards.py` | Core | `format_notification(event, *, channel, locale)` — transforms AppEvents into rich OutboundMessage payloads with ActionButtons and indicator headers; `_EVENT_TEMPLATES` holds the plain-text templates; `LOCALIZED_EVENT_TYPES` lists the events whose card is localized | ✅ |
| `approval_card.py` | Core | `build_approval_card` — `APPROVAL_REQUIRED` card text and buttons per target channel; shows a held reply (`outbound_draft`) with the incoming message, the draft and the expiry outcome; Approve/Deny buttons only for `APPROVAL_CLICK_CHANNELS`, the `/draft` commands for a held reply everywhere else | ✅ |

## Approval Cards

`APPROVAL_REQUIRED` is the one event with a localized, channel-aware card:

- **Language** — copy comes from the channel catalog (`app/channels/i18n`, keys `approval_*`) in the owner's language.
- **Buttons** — Approve/Deny are attached only for `APPROVAL_CLICK_CHANNELS` (Telegram, the only provider whose click reaches the router's approval handler). Every other channel gets a localized "open the app" hint, because a click there never reaches the approval handler.
- **Held reply content** — an `outbound_draft` card quotes the incoming message and the drafted reply (truncated) and lists attachment file names, so the owner can decide in chat. URLs are never shown because they may embed an access token.
- **Deciding by typing** — where there are no buttons, a held reply's card also names the commands that decide it, `/draft approve <code>` and `/draft reject <code>`; `<code>` is `outbound_draft.draft_code(approval_id)`, the first 8 characters of the approval id (`routing/_ARCH.md`, *Held Replies*).
- **Who may press or type** — decided by the router, not here: held replies accept only the owner (`routing/_ARCH.md`, *Owner Check*).

## Configuration

Notification targets are stored in `personalSettings.notificationDeliveries` (array):

```json
{
  "notificationDeliveries": [
    { "channel": "whatsapp", "target": "8613812345678@s.whatsapp.net" },
    { "channel": "telegram", "target": "123456789" }
  ]
}
```

## Lifecycle

- Started in `app/core/channel_bridge/setup.py` after `channel_gateway.start()`
- Stopped before `channel_gateway.stop()`

## Extensibility

New event types only need:
1. Add to `AppEventType` enum in `event_bus.py`
2. Add template to `_EVENT_TEMPLATES` in `adaptive_cards.py`
3. (Optional) Add to `_PUSH_TEMPLATES` in `core/web_push/dispatcher.py` and map click URL in `core/web_push/push_deep_links.py`
