# tasks 模块架构

## 架构概述

异步任务系统 — 消费 harness `toolkits/tasks/` 队列，执行业务 worker 与加密。
上级文档：[../_ARCH.md](../_ARCH.md)。Harness L2：`myrm-agent-harness/src/myrm_agent_harness/toolkits/tasks/TASK_QUEUE_SYSTEM.md`（联调 monorepo 内）。

## 分层

| 层 | 路径 | 职责 |
|----|------|------|
| Harness | `toolkits/tasks/` | `Task`, `SQLiteTaskStore`, `AsyncTaskExecutor` 协议 |
| Harness | `toolkits/llms/{image,video}/async_*_engine.py` | 异步入队 |
| Server | `app/lifecycle/task_worker.py` | Store 单例 + worker 启停 |
| Server | `app/tasks/` | Worker 循环、executor、crypto、事件 |
| Server | `app/api/tasks/` | REST + SSE |
| Frontend | `ImageTaskCard/VideoTaskCard` + `useTasksSubscription` | 进度 UI |

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 任务类型和 worker 导出 | — |
| `worker.py` | 核心 | 任务 worker 主循环。优先级调度、并发控制、超时处理、重试策略、缓存复用。transient 失败按 retry policy 重新置回 `pending` 并写入 `next_retry_at`（datetime）；拉取 `pending` 任务时仅消费 `next_retry_at` 到期任务（未到期任务保持排队）；自动重试时清理 `error/result/started_at/worker*` 等运行残留并把上次失败写入 `metadata.last_error`；终态落库时统一清空 `next_retry_at`，避免残留调度语义；接入 retry/failed/succeeded/timeout/cancel/cache-hit/duration 指标；通过 `on_status_change` 回调发布 `running/pending/failed/succeeded` 事件到 SSE 流 | ✅ |
| `events.py` | 核心 | TaskEventBus：内存 pub/sub 事件总线，SSE 订阅者实时接收 task_update 事件；订阅队列满时有界淘汰最旧事件并投递 `sync_required` 最新事件，避免持续积压导致全量失真；`queue_full` warning 按时间窗节流并携带 suppressed 计数，避免日志风暴 | ✅ |
| `metrics.py` | 辅助 | 任务指标采集（task lifecycle + event bus emitted/dropped/replaced） | — |
| `cleanup.py` | 辅助 | 任务清理（`_db_maintenance_job` 每 6h 调用） | — |
| `image_config_resolver.py` | 核心 | 从 task payload 快照还原 `ImageGenerationConfig`（含 media callback）；密钥经 `task_payload_crypto` 在 persist 前加密 | ✅ |
| `video_config_resolver.py` | 核心 | 从 task payload 快照还原 `VideoGenerationConfig`（含 fallback / media callback）；密钥经 `task_payload_crypto` 在 persist 前加密 | ✅ |
| `task_payload_crypto.py` | 核心 | persist 前递归 seal `api_key` / `gateway_config.auth_token`（含 `fallback_configs`）；worker resolver open 阶段优先当前 key、可用时回退 `CONFIG_ENCRYPTION_KEY_FALLBACKS`/legacy key 解密并剥离明文遗留值 | ✅ |
| `executors/` | 子模块 | 具体任务执行器 | — |

## 子模块

| 模块 | 职责 |
|------|------|
| `executors/` | 图片/视频生成等具体任务执行器（实现 harness `AsyncTaskExecutor`） |

## Key Dependencies

- `myrm_agent_harness.toolkits.tasks` — 队列模型与 store
- `app/lifecycle/task_worker` — `get_task_store()`
