# api/background_tasks/

## 架构概述

后台任务 HTTP 层：查询/取消/恢复离线 Agent 任务，以及 **Shell 进程**（harness registry + BSDL Store）活动视图。
上级文档：[../_ARCH.md](../_ARCH.md)。

`BackgroundTasksPanel` 通过本路由同时展示：
- **Agent 任务** — Kanban 持久化（`/btw`、子 Agent）
- **耗时任务（Shell 执行层）** — 内存 registry 与 Volume 上 `BackgroundJobStore` 合并列表（Web 聊天 `run_in_background`）；GUI 分区标题见 `backgroundTasks.shellSection`

耗时任务：`task_id=shell:{job_id}`（32 位 hex）；服务重启后 Store 中 running 行 reconcile 为 **orphaned**（启动时先停掉比服务活得更久的任务进程组）；已结束任务启动的程序仍在运行时，行带 `leftover_processes`，`POST /{task_id}/cancel` 停的就是这些程序；shell 任务的 cancel 响应带 `leftover_processes`，为停止之后仍活着的程序数（信号发出去不等于程序已停）；这些程序只记在内存里，服务以绕过 `atexit` 的方式退出（崩溃、被强杀）后，重启既不会列出也不会停止它们；`registry_ephemeral=false` 当 Store 已 configure。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Background tasks API — manage /background (/btw /bg) session tasks. | ✅ |
| `router.py` | 路由 | 合并 Kanban + shell；Agent 任务直查 KanbanService + `is_persistent_background()` 过滤（含 `chat_id` 字段供 panel 导航）；暴露 `job_id` / `vault_log_ref` / `waiting_for_input` / `stdin_closed` / `interactive_prompt` / `leftover_processes`；shell cancel 走 harness kill，停完再读一次行，响应带仍存活的 `leftover_processes`；`POST /{task_id}/stdin` GUI 手动 stdin；结构化选项一律经现有 stdin 通道提交；`POST /{task_id}/steer` 的指令先过风险闸门（`reject_if_risky`，命中 400 `risk_held`，不送达任务） | ✅ |
| `test_fixtures.py` | 测试 | local-only Chrome E2E seed（`POST /background-tasks/test/seed-shell-fixture`；`mode=running` / **`running_stdin`** / **`running_stdin_waiting`** / failed / success / completed_with_vault / **`leftover`**（任务结束但它启动的程序仍在运行，该程序忽略 SIGHUP、与 `nohup` 起的守护进程一致，不随后台任务的伪终端挂断退出；响应带 `leftover_marker` 供测试按命令行查找）） | ✅ |
| `test_seed_voice_done.py` | 测试 | local-only voice 完成 seed（`POST /background-tasks/test/seed-voice-done`；构造内存 Kanban voice 任务并发布 `BACKGROUND_TASK_DONE`，驱动 `WebuiVoiceWorkNotifier` → SSE `voice_background_task_done`） | ✅ |

## 依赖

- `app.core.channel_bridge.background_task_handler::ChannelBackgroundTaskHandler` — Kanban agent 任务
- `app.core.channel_bridge.persistent_background::is_persistent_background` — metadata SSOT
- `app.services.agent.shell_background_tasks` — registry + Store 门面
- `app.services.kanban::KanbanService` — Agent 任务持久化（直查 list）
- `myrm_agent_harness.api::resolve_data_dir` — 状态根（`test_fixtures.py` 取默认工作区）
