# adaptive_wakeup/

## 架构概述

后台命令与子智能体完成（结算）后，服务端按有界预算决定这次完成对会话的去向，并只在会话空闲、用户没有叫停时起一轮唤醒回合。每次完成都会在聊天里留一条通知行，下一轮（唤醒的或用户发起的）都能读到。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | ✅ 门面 | 对外入口 `AdaptiveWakeupService`、`get_adaptive_wakeup_service` | ✅ |
| `service.py` | ✅ 核心 | `AdaptiveWakeupService.handle_settlement`：harness 路由按用户停止标记与连续唤醒预算（3 次）决定去向 — 预算内 FOLLOWUP、超额 DEGRADE、用户已停止 SUPPRESS；发布 UI 通知事件、无论哪种去向都写一条通知行（消息 id 为 `wakeup_followup_…` / `wakeup_degraded_…` / `wakeup_suppressed_…`），只有 FOLLOWUP 调度唤醒回合。`record_human_turn`（用户发言：恢复额度、解除停止）、`record_user_stop`（Stop 端点：停止后到期的完成不会起回合） | ✅ |
| `wake_turn_scheduler.py` | ✅ 核心 | `schedule_wake_turn`：唤醒回合的唯一发起处。同一会话已有排队唤醒时合并（只刷新完成时刻）；会话忙时有界等待（上限取网关的目标回合上限）；轮到时在 `server_turn_lease` 下运行，令牌即 Stop / 目标暂停 / E-Stop 翻转的那一个；启动前再核对：E-Stop 已开、用户在通知之后按过停止或又发言、日预算超额都不跑。排队项只由取得会话的那个唤醒移出，运行中到达的完成排成下一个唤醒 | ✅ |

## 边界

- 唤醒回合的构建与流式执行在 `../wakeup_handler.py`（`ServerWakeupHandler.stream_wake_turn`）；本包只决定「要不要起、何时起」，且只经 `schedule_wake_turn` 发起。
- 调用点由 `tests/services/agent/turn_lease/test_server_started_turns_guard.py` 钉死：`stream_wake_turn` 只能由调度器调用，且调度器必须在 `server_turn_lease` 下。
- 预算与停止标记按会话记在 harness 的 `AdaptiveWakeupRouter`（`agent/coordination/adaptive_wakeup/`），本包不重复持有。
- 用户发言的登记点是 `stream_session/chat_history_bootstrap.persist_user_message`（已有会话里的新消息）；Stop 的登记点是 `api/agents/general_agent/streaming.py` 的两个取消端点。

## 依赖

- harness `agent/coordination/adaptive_wakeup`（路由、预算、事件类型）、`agent/security/guards/estop`（`check_estop`）、`utils/runtime/cancellation`
- `app/services/agent/gateway.py`（会话占用判断）、`app/services/agent/turn_lease`（租约）、`app/services/agent/wakeup_handler.py`（唤醒回合）
- `app/services/chat`（通知行落库）、`app/services/event/app_event_bus`（UI 通知）、`app/services/budget/enforcer`（日预算）
