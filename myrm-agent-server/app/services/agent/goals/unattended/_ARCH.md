# unattended/

## 架构概述

服务端为目标自己开的无人值守回合：队列 dequeue / 后台任务结束后的 WAIT 恢复 / loop_restart / 恢复与解除等待后的续跑，统一经这里启动无头 agent 流；启动失败后目标的去向也只在这里决定。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | ✅ 门面 | 对外入口：`trigger_goal_stream` / `trigger_goal_stream_with_failure_policy`、失败策略与通知函数 | ✅ |
| `trigger.py` | ✅ 核心 | 无头 stream 触发；从 chat 绑定 profile 注入 `agent_id` + `user_instructions`（team protocol + output suffixes + `subagent_ids` + `agent_skill_ids` + `enabled_builtin_tools` → `resolve_agent_mount(WEB_CHAT)` + `agent_security_raw`/`enable_web_fetch`，与 Web turn1 对齐）；`GeneralAgentParams` 显式注入 `enable_memory=resolve_memory_enabled(...)`（与 cron/kanban 一致），并走 `build_agent_runtime_context` 注入 `goal_provider`（会话 GoalProvider，使 goal 生命周期「受保护路径/终态回调/dequeue」在 unattended 运行中保持激活）+ `execution_mode` + `disabled_skill_roots`（与其余入口对齐）；回合在构建 agent 之前先取 `turn_lease.server_turn_lease`（预留会话 + 注册取消令牌，与聊天回合同一组原语），因此暂停、聊天「停止」与 E-Stop 能真正中断它，Stop 后续跑守卫也能把目标置为暂停，被取消的回合结束后台任务；会话已被另一回合占用（`AgentBusyError`：同一目标被连点恢复、或恢复期间用户发了消息）或应用正在排空（`AgentDrainingError`）不是目标失败——记 info 后让位，目标状态不动；回合以任何方式结束租约都归还令牌与自己的预留（不会释放期间抢到会话的消息回合的预留）；失败处理委托 `failure.py` | ✅ |
| `failure.py` | ✅ 核心 | 无人值守目标流失败后的目标去向 SSOT：`handle_unattended_goal_stream_failure`（setup + runtime → NEEDS_HUMAN_REVIEW 或 keep ACTIVE + SSE；仅升级仍为 ACTIVE 的目标，已被 run 停放/暂停/完成的目标保持原状态）、`TriggerFailurePolicy`；`resolve_user_locale` 供通知复用；`publish_goal_needs_review_notification` 供 orphan WAIT 恢复复用 | ✅ |

## 边界

- 调用方（`goal_controls.continue_resumed_goal`、`usage_limit_resume.daemon` / `notify`、`goal_wait_background_resume`、`goal_wait_orphan_recovery`、`goal_learnings`）只从包门面导入；`trigger.py` 与 `failure.py` 之间直接互引，不经门面。
- 服务端自启的回合没有 HTTP 流，取消只能经会话占用与 `CancellationRegistry` 令牌到达；三处自启入口（本包、`streaming_support/hitl_timeout.py`、`lifecycle/auto_continue.py`）共用 `turn_lease`，调用点由 `tests/services/agent/turn_lease/test_server_started_turns_guard.py` 钉死。

## 依赖

- 父模块 [`goals/_ARCH.md`](../_ARCH.md)
- `app/services/agent/gateway.py`（`AgentBusyError` / `AgentDrainingError`）、`app/services/agent/turn_lease/`（会话占用 + 取消令牌）、`app/services/agent/streaming.py`（`ai_agent_service_stream`）
