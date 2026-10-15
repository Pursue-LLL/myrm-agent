# goals/

## 架构概述

Goal 业务域：会话级 Goal 句柄注册、draft 生成、unattended headless 流触发与 WAIT/orphan 生命周期恢复。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `goal_registry.py` | ✅ 核心 | 会话级 Goal 句柄全局注册表。`ServerGoalManager` 扩展 harness `GoalManager`，Goal 完成时收集 session artifacts 写入 metadata.deliverables 供前端 bundle 展示；semantic judge 通过 `load_platform_llm()` + `extract_answer_text` 读 WebUI 默认模型（wire-aware，无 env fallback），评估截图仅在屏幕非 LOCKED/SLEEPING 时采集（`_screen_is_capturable`），锁屏态降级为纯文本判定，评估器不发起解锁；`session_ids()` 列出存活会话供分支监视器遍历 | ✅ |
| `goal_branch_stash.py` | ✅ 核心 | 分支感知：`check_and_handle_branch_stash` 在 git 分支变化时处理会话的 Goal 与 todo——目标分支没有 stash 则活跃 Goal 迁移过去，有则暂存旧分支并恢复目标分支的 stash；stash 的有无与存取只走 harness 公开 API（`GoalStorage.get_stash`、`GoalProvider.stash_goal/restore_goal`），本模块只持有 `goals_last_branch/{session_id}` 这一个键；`start_branch_watcher` 每 0.5s `os.stat(.git/HEAD)`，mtime 变化时遍历存活会话；变化后更新 Kanban 分支元数据并发布 `goal:branch_switched` | ✅ |
| `goal_stream_trigger.py` | ✅ 核心 | Goal 队列 dequeue / bg WAIT resume / loop_restart 统一 unattended headless stream；从 chat 绑定 profile 注入 `agent_id` + `user_instructions`（team protocol + output suffixes + `subagent_ids` + `agent_skill_ids` + `enabled_builtin_tools` → `resolve_agent_mount(WEB_CHAT)` + `agent_security_raw`/`enable_web_fetch`，与 Web turn1 对齐）；`GeneralAgentParams` 显式注入 `enable_memory=resolve_memory_enabled(...)`（与 cron/kanban 一致），并走 `build_agent_runtime_context` 注入 `goal_provider`（会话 GoalProvider，使 goal 生命周期「受保护路径/终态回调/dequeue」在 unattended 运行中保持激活）+ `execution_mode` + `disabled_skill_roots`（与其余入口对齐）；`handle_unattended_goal_stream_failure` SSOT（setup + runtime → NEEDS_HUMAN_REVIEW 或 keep ACTIVE + SSE）；`publish_goal_needs_review_notification` 供 orphan WAIT 恢复复用 | ✅ |
| `goal_wait_background_resume.py` | ✅ 核心 | background job finish 匹配 `wait_on_background_job_id` → exit_wait → `trigger_goal_stream_with_failure_policy(needs_human_review)`；前端 refreshActiveGoal 同步 Card | ✅ |
| `goal_wait_orphan_recovery.py` | ✅ 核心 | 启动时在 Store reconcile 之后：WAIT + orphaned background pid → NEEDS_HUMAN_REVIEW + goal_needs_review SSE（对称 `pause_orphaned_active_goals`） | ✅ |
| `goal_draft.py` | ✅ 辅助 | Goal 创建前 draft — 从 objective 生成 constraints / acceptance_criteria（Server lite LLM） | ✅ |

## 依赖

- 父模块 [`agent/_ARCH.md`](../_ARCH.md)
- harness `agent/goals/*`（GoalManager / GoalStorage / wait_background_bash）
