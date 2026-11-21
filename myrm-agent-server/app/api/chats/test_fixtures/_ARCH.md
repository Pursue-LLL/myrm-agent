# api/chats/test_fixtures/

## 架构概述

local-only Chrome E2E seed 路由子包。上级文档：[../_ARCH.md](../_ARCH.md)。

`__init__.py` 为聚合门面：include `_inline_core`、`_kanban` 与全部 23 个子模块的 router。上层通过 `from ..test_fixtures import router` 挂载。

所有 seed 端点以 `POST /chats/test/seed-*` 暴露，`include_in_schema=False`，且仅 local/tauri 模式可用（`is_local_mode` 守卫）。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 聚合门面：挂载 `_inline_core`、`_kanban` 与全部子模块 |
| `_inline_core.py` | 核心 seed：citation / skill chip transcript / skill chip composer / embed |
| `_kanban.py` | Kanban seed：closure / IN_REVIEW |
| `allowed_tools_recovery.py` | allowed_tools recovery seed |
| `artifact_share.py` | 制品分享页 seed（`POST /chats/test/seed-artifact-share-fixture`：同一会话下登记两份制品，Chart.js 图表页与带脚本 / 事件处理器 / `javascript:` 链接的 Markdown 报告；各占一个文件夹，按聊天工作区根登记，与分享链接读取文件的根一致） |
| `chat_share.py` | Chat Share 生命周期 seed（chat + user/assistant 消息，公开分享页可渲染） |
| `clarify_refresh.py` | clarify refresh HITL hydrate seed（pending/answered/regenerate_sibling/structured_form） |
| `context_retention.py` | context retention seed（compacted summary + pins + snapshot bookmarks） |
| `copilot.py` | Lean Co-Pilot seed（assistant markdown + active run digest） |
| `deliverable.py` | deliverable link seed（workspace 文件 + inline deliverable markdown） |
| `evicted.py` | UECD evicted LiveTerminal seed |
| `file_edit_batch.py` | file_edit batch live/read_ui + workspace-only seed |
| `file_mutation.py` | file mutation seed |
| `guardrail_bash.py` | guardrail bash Badge seed |
| `media_cards.py` | 生成媒体卡片 seed（`POST /chats/test/seed-media-cards-fixture`：图像任务 / 视频任务 / 同步图像编辑 / 语音各一条已登记条目，媒体经落库回调真实存储；`address=file` 为任务结果指向不可加载地址的负向对照，`address=expired` 为任务记录已不存在） |
| `memory_lifecycle.py` | memory lifecycle seed |
| `prior_chat.py` | composer @chat: mention seed |
| `revert.py` | RevertFiles seed（chat + snapshot data） |
| `rich_media_preview.py` | workspace rich-media preview seed（png/pdf/zip/txt 落盘） |
| `security_preset.py` | SecurityPreset seed（agent-bound chats） |
| `stream_retry_busy.py` | stream retry busy seed |
| `tool_history_recovery.py` | tool_history_recovery progress step seed |
| `wechat_draft.py` | WeChat Official draft seed |
| `wiki_dedup.py` | wiki corpus dedup seed（duplicate raw + sync scan） |
| `wiki_pending_drift.py` | wiki pending review 分页与计数漂移自愈 seed / cleanup（标记前缀的待审草稿经真实 WikiPendingEditsManager 写入） |
| `wiki_provenance.py` | wiki provenance gap seed（compiled concept missing sources） |

## 依赖

- `app.services.chat.chat_service` — 会话/消息持久化
- `app.services.agent.agent_service` — E2E seed 选取 agent scope
- `app.services.kanban.KanbanService` — Kanban seed 的看板/任务持久化（`_kanban.py`）
- `myrm_agent_harness.toolkits.kanban.types` — TaskPriority/TaskStatus/source_chat metadata SSOT（`_kanban.py`）
- `myrm_agent_harness.api::resolve_data_dir` — 状态根（`evicted.py` 取默认工作区）
- `app.ai_agents.media_tools.media_persist` / `app.lifecycle.task_worker.get_task_store` — 生成媒体的落库回调与任务存储（`media_cards.py`）
- `app.core.artifacts.LocalArtifactProcessor` / `app.services.agent.params.workspace_resolve` — 与对话运行同一入口登记制品、取聊天工作区根（`artifact_share.py`）
