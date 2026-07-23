# services/files 模块架构

## 架构概述

文件内容提取与 revert 快照 hydrate/cleanup 服务。为 Kanban 附件、Agent 工具、revert API、channel /undo 等非 HTTP-only 路径提供能力，复用 Harness file_parsers / SnapshotStore，不依赖 `app/api/files` 路由层。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `content_extraction.py` | ✅ 核心 | PDF/Office 提取（bytes/path）；`api/files` 与 Kanban 共用 | ✅ |
| `attachment_settings.py` | ✅ 核心 | `extractDocumentText` 个人设置解析（默认开启） | — |
| `revert_hydrate.py` | ✅ 核心 | 跨请求 SnapshotStore 磁盘 hydrate + revert 后 cleanup；root 顺序：`WORKSPACE_ROOT` → `resolve_workspace_root()` → chat.workspace_dir → default chat workspace（`resolve_workspace_root` 须在 default workspace 之前，避免 resolver 缓存被污染） | ✅ |
| `revert_agent_notify.py` | ✅ 核心 | Turn revert 成功后 push harness `restore_inbox`（与 Shadow Git restore 同 inbox，snapshot_id 前缀 `turn:` / `session:`） | ✅ |

## 依赖关系

### 内部依赖
- `myrm_agent_harness.toolkits.file_parsers`：PDF/Docx/Excel/Pptx 解析

### 被依赖方
- `app/api/files/revert.py`：revert HTTP API hydrate/cleanup + Agent restore_inbox 通知
- `app/core/channel_bridge/turn_handler.py`：channel /undo·/retry 文件 revert cleanup + Agent restore_inbox 通知
- `app/services/kanban/task_runner.py`：任务附件上下文注入
- `app/channels/media/document_enrichment.py`：渠道入站文档提取
