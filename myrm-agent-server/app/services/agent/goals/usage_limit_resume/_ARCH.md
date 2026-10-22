# usage_limit_resume/

## 架构概述

目标遇到提供方额度上限（harness 把目标停放为 WAIT，`wait_kind=usage_limit` + `wait_resume_at`）后的宿主侧闭环：到点唤醒、用户通知、手动「立即重试」。harness 负责判定与停放，本包只负责让停放在宿主上真正生效。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | ✅ 门面 | 对外入口：hold 回调、守护进程、手动重试 | ✅ |
| `daemon.py` | ✅ 核心 | `UsageLimitWakeDaemon`：内存 armed 集合 + 单个挂钟轮询任务（≤30s，空集合时空转）；启动时从存储重建；唤醒前重读目标、会话忙/排空则延后、晚于 24h 暂停；`resume_goal_after_usage_limit` 供 REST「立即重试」；`next_due_at()` 返回最早 armed 时间供托管唤醒上报读取；`WAKE_OWNER` 所有权标记使仅经 `on_goal_hold` 停放的目标被本守护进程唤醒 | ✅ |
| `hold.py` | ✅ 核心 | `build_goal_hold_callback`：`on_goal_hold` 回调——打所有权标记、arm 守护进程、发通知 | ✅ |
| `notify.py` | ✅ 辅助 | `publish_goal_usage_limit_notification`：wait / resumed / paused 三态 SYSTEM_NOTIFICATION（文案不含时间与技术细节） | ✅ |

## 边界

- 目标被停放并收到 `on_goal_hold` 需同时满足两个条件：① 流上下文携带 `goal_provider`——写入点只有会话编排器（`app/services/agent/stream_session/orchestrator_turn_body.py`）、无人值守目标流（`app/services/agent/goals/goal_stream_trigger.py`）与 Kanban（`app/services/kanban/task_runner/runner.py`）；IM 渠道回合经 `build_agent_runtime_context` 构建上下文，不含 goal 字段，遇额度错误走常规报错回复，不停放；② 目标键与流会话键一致。
- Kanban 目标存于 `kanban:<task_id>`，而其流以裸 `task_id` 运行，不满足②：停放查无目标 → 走类型化异常，由 Kanban 调度器按 `cooldown_remaining_ms` 延后重试（`SCHEDULED`），因此从不被打标记、从不被本守护进程唤醒。Cron 回合不写入 `goal_provider`（不满足①），同样由其调度器重试。
- 唤醒由宿主进程内的守护进程执行，进程不运行的时段无法准点唤醒：本机休眠、托管部署中空闲被平台回收器暂停的沙箱均属此类。进程恢复运行后，到期目标在一个轮询周期内补发唤醒（进程重启时先由 `_rebuild` 从存储重建并留 `_STARTUP_GRACE_S` 缓冲）；迟到超过 24h（`PROVIDER_WINDOW_HOLD_MAX_S`）则暂停并通知。托管沙箱被空闲回收器暂停时，由 [`services/sandbox_wake`](../../../sandbox_wake/_ARCH.md) 读取本守护进程的 `next_due_at()`（最早 armed 时间）上报控制平面，由控制平面到点唤醒沙箱；本包只暴露该时间，不感知控制平面。
- 恢复路径复用 `goal_stream_trigger.trigger_goal_stream_with_failure_policy`（unattended，yolo 强制），不引入第二条续跑通道。

## 依赖

- 父模块 [`goals/_ARCH.md`](../_ARCH.md)
- harness `api`（`GOAL_WAIT_*` / `pause_goal_after_missed_wake` / `ProviderWindowHint`）
