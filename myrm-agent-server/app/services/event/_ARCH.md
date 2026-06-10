# event 服务模块


---

## 架构概述

Agent 事件系统：Turn 生命周期持久化 + 全局 SSE AppEvent 总线（Kanban/记忆/技能等实时推送）。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `app_event_bus.py` | ✅ 核心 | AppEventType / AppEvent / get_event_bus 单例 | ✅ |
| `types.py` | ✅ 核心 | Turn 事件类型枚举 | ✅ |
| `recorder.py` | ✅ 核心 | EventRecorder — 单 Turn 事件持久化 | ✅ |
| `turn_manager.py` | ✅ 核心 | TurnManager — Turn 生命周期 | ✅ |

---

## 依赖关系

### 内部依赖
- `app/config/deploy_mode`：本地模式检测
- `app/database/`：AgentEvent、AgentTurn 模型

### 被依赖方
- `app/api/events/`：事件 API 路由
- `app/server/warmup.py`：启动时 stale turn recovery（PENDING/RUNNING → INTERRUPTED）
- `app/core/channel_bridge/btw_notifier.py`：订阅 `BACKGROUND_TASK_DONE` 事件回推结果到原始渠道
- `app/core/notifications/dispatcher.py`：订阅多类 EventBus 事件推送到用户配置的通知渠道
