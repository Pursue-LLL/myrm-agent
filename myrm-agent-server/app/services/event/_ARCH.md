# event 服务模块

---

## 架构概述

全局 SSE AppEvent 总线（Kanban/记忆/技能等实时推送）。

agent 事件 SSOT 为 harness JSONL event-log（`FileEventLogBackend`），云合规审计经 `app/api/internal/agent_audit.py` 暴露。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `app_event_bus.py` | ✅ 核心 | AppEventType / AppEvent / ServerEventBus / get_event_bus 单例（含 `WORKSPACE_FILE_CHANGED`、`RUN_DIGEST_UPDATED`、`SKILL_POOL_UPDATED`） | ✅ |

---

## 依赖关系

### 内部依赖
- `app/config/deploy_mode`：本地模式检测

### 被依赖方
- `app/core/channel_bridge/btw_notifier.py`：订阅 `BACKGROUND_TASK_DONE` 事件回推结果到原始渠道
- `app/core/notifications/dispatcher.py`：订阅多类 ServerEventBus 事件推送到用户配置的通知渠道
