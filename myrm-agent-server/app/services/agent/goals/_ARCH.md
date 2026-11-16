# goals/

## 架构概述

Goal 业务域：会话级 Goal 句柄注册、draft 生成、unattended headless 流触发与 WAIT/orphan 生命周期恢复。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `goal_registry.py` | ✅ 核心 | 会话级 Goal 句柄全局注册表。`ServerGoalManager` 扩展 harness `GoalManager`，Goal 完成时收集 session artifacts 写入 metadata.deliverables 供前端 bundle 展示；semantic judge 通过 `load_platform_llm()` + `extract_answer_text` 读 WebUI 默认模型（wire-aware，无 env fallback），评估截图仅在屏幕非 LOCKED/SLEEPING 时采集（`_screen_is_capturable`），锁屏态降级为纯文本判定，评估器不发起解锁；`register()` 为一个回合新建 provider 并登记（同会话的旧条目被替换，回合的内存状态只属于它自己），`unregister(session_id, provider)` 带着该 provider 归还，条目已是别的回合的则不动（网关在回合收尾结束之前就归还会话，服务端可在这段时间内启动同一会话的下一个回合，较早回合的晚归还不会摘掉它）；`session_ids()` 列出存活会话供分支监视器遍历；`get_provider()` 只给运行中回合的句柄（回合之间为 None）；聊天回合由编排器 `register`、流收尾按自己的 provider 归还；`turn_provider()` 是服务端自启回合（无人值守目标续跑）的登记句柄：回合开始时登记、以任何方式结束都按自己的 provider 归还；`resolve_provider()` 供 HTTP API、IM 命令与回合之外的服务端逻辑（终态/续跑回调、后台作业恢复、回滚暂停、额度唤醒、看板解除阻塞）以及 agent 构建（IM、Cron、唤醒回合不登记 provider）读写目标：会话有注册的就用注册的，回合之间则返回一个绑定该会话、读同一份存储的 `ServerGoalManager`（完成目标时同样收集交付物），且不注册它（注册表只放运行中会话的句柄，`GET /goals/active` 按它遍历）；`has_active_goal()` 读存储判断会话是否有 ACTIVE Goal（与 provider 是否注册无关，provider 只在回合内注册），供 execution_cache 指纹使用 | ✅ |
| `goal_branch_stash.py` | ✅ 核心 | 分支感知：`check_and_handle_branch_stash` 在 git 分支变化时处理会话的 Goal 与 todo——目标分支没有 stash 则活跃 Goal 迁移过去，有则暂存旧分支并恢复目标分支的 stash；stash 的有无与存取只走 harness 公开 API（`GoalStorage.get_stash`、`GoalProvider.stash_goal/restore_goal`），本模块只持有 `goals_last_branch/{session_id}` 这一个键；todo 按 session 取放（同一工作区里每个 chat 一份清单，切分支只搬走切换的这个 session 的）；`start_branch_watcher` 每 0.5s `os.stat(.git/HEAD)`，mtime 变化时遍历存活会话；检查经 `resolve_provider` 取 provider，自己不登记任何东西（IM `/goal` 与监视器都在回合之外调它）；变化后更新 Kanban 分支元数据并发布 `goal:branch_switched` | ✅ |
| `unattended/` | ✅ 核心 | 服务端为目标自启的无人值守回合：`trigger_goal_stream*`（队列 dequeue / 后台 WAIT 恢复 / loop_restart / 恢复后续跑；回合先预留会话并注册取消令牌，暂停、Stop、E-Stop 才能真正中断它；会话仍被刚结束目标的回合占用时，启动先有界等待它归还；回合内还登记会话的 provider，agent 才挂得上目标工具、目标回调才接得上）与失败去向 SSOT。详见子目录 `_ARCH.md` | ✅ |
| `goal_wait_background_resume.py` | ✅ 核心 | background job finish 事件带的是起作业那一轮的会话键 `chat_<id>`，而目标按聊天 id 存放：先转成聊天 id（`chat_id_from_session_id`），再经 `resolve_provider`（作业结束时通常没有回合在跑）取目标，匹配 `wait_on_background_job_id` → exit_wait → `trigger_goal_stream_with_failure_policy`；前端 refreshActiveGoal 同步 Card | ✅ |
| `goal_wait_orphan_recovery.py` | ✅ 核心 | 启动时在 Store reconcile 之后：WAIT + orphaned background pid → NEEDS_HUMAN_REVIEW + goal_needs_review SSE（对称 `pause_orphaned_active_goals`）；作业台账按起作业的会话键 `chat_<id>` 记录、目标按聊天 id 存放，台账先转成聊天 id 再与目标匹配 | ✅ |
| `usage_limit_resume/` | ✅ 核心 | 提供方额度上限后的宿主闭环：`on_goal_hold` 回调（打所有权标记 + arm + 通知）、挂钟轮询唤醒守护进程（启动重建、忙/排空延后、>24h 暂停）、手动「立即重试」。详见子目录 `_ARCH.md` | ✅ |
| `goal_controls.py` | ✅ 核心 | Web 卡片与 IM 指令共用的 Goal 控制规则：`NON_TERMINAL_GOAL_STATUSES`、`select_cancellable_goal`（运行中的目标，否则仍未结束的最新目标，作为取消/清除的对象）、`stop_goal_turn`（暂停/取消一个目标后，登记「用户已停止」让此后到期的后台完成不再自行起回合，直到用户或目标恢复；正在干活的目标另用聊天「停止」按钮同一组信号中断它的回合；等待中/待复核/预算受限的目标不碰会话里的当前回合）、`note_goal_resumed`（目标恢复即解除上述压制）、`is_turn_stopping` / `wait_for_stopped_turn`（恢复前有界等待被叫停的回合收尾，避免它的续跑守卫把刚恢复的目标再次暂停；等不到则返回 False，调用方拒绝本次恢复；没被叫停的在途回合（用户同时发的消息）不拖慢恢复）、`can_start_goal_turn`（应用未排空且会话没有在途回合）、`continue_resumed_goal`（恢复后启动无人值守继续回合；`can_start_goal_turn` 为假时不启动） | ✅ |
| `goal_draft.py` | ✅ 辅助 | Goal 创建前 draft — 从 objective 生成 constraints / acceptance_criteria（Server lite LLM） | ✅ |

## 依赖

- 父模块 [`agent/_ARCH.md`](../_ARCH.md)
- harness `agent/goals/*`（GoalManager / GoalStorage / wait_background_bash）
