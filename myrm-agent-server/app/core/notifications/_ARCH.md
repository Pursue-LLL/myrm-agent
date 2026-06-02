# Notifications Module Architecture

## Purpose

Event-driven IM notification dispatch. Subscribes to the global `EventBus`
and pushes human-readable notifications to user-configured IM channels
(multi-channel) via `ChannelGateway.publish()`.

边界约束：
- 本模块只负责“消息投递”，不是审批事实源
- `Review Inbox` 的真实待审数据来自 `PendingMemory`、审批主链上的 evolution records，以及 migration pending records
- 如需提醒用户有待审项，可以复用通知模块发送提醒，但不能把通知记录当成审批状态来源

## Data Flow

```
 pairing_store / approvals / health / budget / skills / channels / ...
       ↓ publish(AppEvent)
    EventBus (fan-out)
     ↓               ↓
  SSE (Web)    NotificationDispatcher (IM)
                      ↓ _format_message()
               ChannelGateway.publish()
                      ↓
               WhatsApp / Telegram / Slack / Feishu / ...
```

### Supported Event Templates

| AppEventType | IM Push | Trigger Source |
|---|---|---|
| `PAIRING_PENDING` | ✅ | `pairing_store` |
| `APPROVAL_REQUIRED` | ✅ | `approvals/registry` |
| `HEALTH_ALERT` | ✅ | `health/router` |
| `BUDGET_ALERT` | ✅ | `budget/enforcer` |
| `NEW_SKILL_DRAFT` | ✅ | `skills/draft_notification` |
| `MESSAGE_DEAD_LETTERED` | ✅ | `channels/__init__` |
| `CHANNEL_DISCONNECTED` | ✅ | `channels/setup` |
| `WECHAT_SESSION_EXPIRED` | ✅ | (reserved) |
| `CONFIG_HEALTH_WARNING` | ✅ | `config/health_monitor` |
| `SYSTEM_NOTIFICATION` | ✅ | `lifecycle/system` |
| `KANBAN_TASK_UPDATED` | ✅ (terminal only) | `services/kanban/service` — completed/blocked/failed actions trigger IM push; lifecycle events silently skipped |
| `GOAL_TERMINAL` | ✅ | `ai_agents/general_agent/goal_learnings` — pushed when a Goal reaches terminal state (complete/cancelled/budget_limited/needs_human_review); IM message includes files_modified, total_tokens and total_cost_usd statistics |

Events not in `_EVENT_TEMPLATES` (e.g. `IDLE_STATUS`, `SKILL_INSTALL_PROGRESS`)
are silently skipped — they are high-frequency or internal and not suitable for IM push.

## Files

| File | Role | Description |
|------|------|-------------|
| `dispatcher.py` | Core | `NotificationDispatcher` — subscribes to EventBus, formats messages, sends to all configured targets via Gateway |

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
2. Add template to `_EVENT_TEMPLATES` in `dispatcher.py`
