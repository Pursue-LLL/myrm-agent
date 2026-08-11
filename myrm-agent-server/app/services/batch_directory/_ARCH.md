# services/batch_directory/

## 架构概述

批量目录并行 Prompt 编排业务服务：**同一 prompt × N 目标目录**并行执行。执行完全委托 Kanban 调度器/运行器——每个目标目录生成一个 Kanban 任务（`workspace_path` 指向该目录，metadata 标记 `batch_project_id`）；本服务只负责批次级编排：批量建板/建任务、聚合统计、终态检测通知、取消。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 `BatchDirectoryService` 与 `fetch_project_task_models` | — |
| `service.py` | 核心 | 批次编排：`create_project`（建板+扇出任务）、`cancel_project`（先原子置 cancelled 防竞态，再 RUNNING 取消、IN_REVIEW reject、归档）、`delete_project`（有 active 任务时拒绝）、`dispatcher_event_hook`（Kanban 事件终态检测 → `maybe_finalize` → SystemNotification）；只读聚合委托 `_read.py`、重试/重跑委托 `_retry.py`、暂停/恢复/审批委托 `_lifecycle.py` | ✅ |
| `_read.py` | 辅助 | 只读聚合：`list_projects`/`get_project`（latest-per-directory 聚合+产物校验+终态自愈调度）、`_resolve_artifact_results`（任务产物 glob 校验聚合）、`_schedule_finalize_if_due`（读取路径终态自愈） | ✅ |
| `_retry.py` | 辅助 | 重试/重跑：`retry_failed`（失败/缺产物目录重发新任务并重开项目）、`retry_task`（单目录重试）、`rerun_project`（全量重跑，仅终态项目）、`_fan_out`/`_next_attempt`/`_is_retryable_task`/`_retryable_directories` | ✅ |
| `_lifecycle.py` | 辅助 | 生命周期：`pause_project`（cancel 运行中执行后统一冻结可执行任务为 BLOCKED，多轮收敛消除 dispatcher 重拾/并发新建窗口）、`resume_project`（按 `batch_pause` 标记解冻并重开项目）、`approve_all_results`（批量审批）；`_ProjectSettings`/`_load_project_snapshot`/`_require_not_paused` 共享快照 | ✅ |
| `_run.py` | 辅助 | 任务扇出助手：`fan_out_batch_tasks` 为一组目录装配同 prompt 的 Kanban 任务并写入单调 `batch_attempt` 代次（创建/重试/重跑共用），单目录建任务失败不阻断整批 | — |
| `_helpers.py` | 辅助 | 序列化/查询/路径校验/产物 glob 校验助手：`_project_to_dict`、`_aggregate_statuses`、`_resolve_directory`、`fetch_project_task_models`、`_artifact_status_for_task`、`_failed_directory_paths`、`_validate_artifact_patterns`、`_latest_tasks_per_directory`/`_task_attempt`/`_is_later_task`（每目录取最新任务）、`_reopen_running`（项目回置 running 并刷新聚合）、`_send_completion_notification` | ✅ |

## 领域职责

- **单一事实来源**：任务真值在 `kanban_tasks`，本表只存批次元数据 + 运行聚合；`list_projects`/`get_project` 实时从任务表聚合刷新计数。
- **批板语义**：未指定 `board_id` 时自动创建专用 board（并发上限 = 批次 `concurrency`，`require_approval` 透传）。
- **执行上下文**：每个任务 `workspace_path` 指向目标目录；`artifact_patterns` 与产物要求经任务 metadata `context_annotations` 由 KanbanTaskRunner 注入 agent 上下文（`_augment_context`），使 agent 明确工作目录与交付标准。
- **终态检测**：通过 `dispatcher_event_hook` 监听 Kanban 任务终态事件（task_completed/task_failed/task_blocked/task_archived），全部终态时置 `status` 并发送 SystemNotification（完成/失败 + 缺产物目录）。REST 手动移动任务到终态不产生 dispatcher 事件，由 `get_project`/`list_projects` 读取路径自愈（`_schedule_finalize_if_due` 触发幂等 `maybe_finalize`）。`paused` 状态不在终态集合，暂停期间 dispatcher 事件与读取自愈均跳过终态判定，保证冻结稳定。`_schedule_finalize_if_due` 与 `maybe_finalize` 均显式排除 `paused`，恢复后由 `get_project` 重新判定。
- **并发安全**：`maybe_finalize` 使用条件 UPDATE（`status NOT IN 终态`）原子迁移项目状态，唯一赢家发送通知，重复事件/自愈并发调用不产生重复通知；`cancel_project` 先原子置 `cancelled` 再归档任务，归档触发的 `task_archived` 事件在终态下跳过 `maybe_finalize`，避免误报失败。
- **聚合口径（latest-per-directory）**：重试/重跑后同一目录存在多条任务记录，所有聚合与终态判定仅取每目录最新任务（按 `batch_attempt` 单调代次排序，`created_at` 秒级精度不足以区分同秒重试），保证 `total_tasks` 恒等于目录数、重试成功后项目可达 `completed`。
- **artifact glob 校验**：任务完成后对 `workspace_path` 执行 `artifact_patterns` glob 匹配（`asyncio.to_thread` 不阻塞事件循环）；每任务结果写入 `artifact_status`（verified/missing/not_specified），项目级缺失目录聚合到 `missing_artifact_directories` 并随通知上报。创建时经 `_validate_artifact_patterns` 拒绝绝对路径、空 pattern 与 `..` 穿越。
- **取消语义**：`cancel_project` 对 RUNNING 任务先 `cancel_task_execution`（停止 agent 执行、不浪费算力）、对 IN_REVIEW 任务先 `reject_task`（走审批拒绝流程），再 `move_task(ARCHIVED)`，其余非终态任务直接归档。
- **暂停/恢复**：`pause_project` 置项目 `paused` 中间态，对所有可执行任务（READY/BACKLOG/RUNNING）先 `cancel_task_execution` 中断 agent 执行、再置 `BLOCKED(HUMAN, batch_pause)` 防 dispatcher 拾取，多轮重新拉取收敛 dispatcher 重拾与并发重试新创建的任务；`resume_project` 按 `batch_pause` 标记解冻全部冻结任务，并回置 `running`（无冻结任务残留时同样回置，由读取自愈收尾终态；解冻全部失败时保持 `paused` 防卡死）。暂停期间终态检测被抑制，项目保持冻结；暂停后重试/重跑被 `_require_not_paused` 拒绝，取消与批量接收仍可用。
- **批量接收**：`approve_all_results` 将项目所有 IN_REVIEW 任务批量 approve 为 COMPLETED，使 `require_approval` 批次可一键收尾进入终态判定。
- **重试/重跑**：`retry_failed` 对 `failed`/`archived`/已 `completed` 但缺产物的目录重发新任务并回置 `running`；`retry_task` 支持单目录重试（仅最新任务且可重试时）；`rerun_project` 全量重跑所有目录（仅终态项目，防止与在途任务产生重复）；无重试目标时保持原状态并返回空结果。`delete_project` 在存在非终态任务时拒绝删除（提示先取消）。
- **原子创建**：`create_project` 任一目录建任务失败即整体失败（HTTP 400），并回滚已建任务为 `ARCHIVED`，避免半成品批次静默丢弃目录（无任务目录在聚合与重试中均不可见）；重试/重跑路径容忍部分失败，因为失败目录保留原任务且仍可重试。

## 内部依赖

- `app.database.models.batch_directory.BatchDirectoryProjectModel` — 批次元数据 ORM
- `app.services.kanban.KanbanService` — `add_task`/`move_task`/`cancel_task_execution`/`create_board`
- `app.services.infra.system_notification.SystemNotificationService` — 完成/失败通知
- `myrm_agent_harness.agent.security.path_security.is_dangerous_path` — 目录安全校验
- `app.database.connection.get_session` — async session
