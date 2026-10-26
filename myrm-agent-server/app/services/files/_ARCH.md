# services/files 模块架构

## 架构概述

文件内容提取、revert 快照 hydrate/cleanup、workspace organize HITL 批量整理，以及人工文本编辑的字节级读写服务。为 Kanban 附件、Agent 工具、revert API、channel /undo、organize API 等非 HTTP-only 路径提供能力，复用 Harness file_parsers / SnapshotStore / path_security，不依赖 `app/api/files` 路由层。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `content_extraction.py` | ✅ 核心 | PDF/Office 提取（bytes/path）；`api/files` 与 Kanban 共用 | ✅ |
| `attachment_settings.py` | ✅ 核心 | `extractDocumentText` 个人设置解析（默认开启） | — |
| `revert_hydrate.py` | ✅ 核心 | 跨请求 SnapshotStore 磁盘 hydrate + revert 后 cleanup；root 顺序：`WORKSPACE_ROOT` → `resolve_workspace_root()` → chat.workspace_dir → default chat workspace（`resolve_workspace_root` 须在 default workspace 之前，避免 resolver 缓存被污染） | ✅ |
| `revert_agent_notify.py` | ✅ 核心 | Turn revert 成功后 push harness `restore_inbox`（与 Shadow Git restore 同 inbox，snapshot_id 前缀 `turn:` / `session:`） | ✅ |
| `organize/` | ✅ 核心 | workspace organize HITL：plan 校验、批量移动、job 回滚、wikilink 重写；详见 [organize/_ARCH.md](organize/_ARCH.md) | ✅ |
| `text_edit_io.py` | ✅ 核心 | 人工编辑文本文件的字节级 I/O：sha256 版本令牌、可编辑判定（二进制 / 非 UTF-8 / 混合换行 / >1 MiB 只读）、按文件自身换行与 BOM 还原、`write_text_if_version` 比对保存（每路径进程内锁 + 原子替换并保留权限位 + `os.access` 只读守卫 + 仅 Windows 的有界 `PermissionError` 重试）、`create_text_file_exclusive`（`O_EXCL` 副本）；不依赖 HTTP 层 | ✅ |
| `reveal_utils.py` | ✅ 辅助 | Local reveal/open/Obsidian launcher（macOS/Windows/Linux）；`local_actions` 与 `/wiki/vault/*` 共用 | ✅ |

## 依赖关系

### 内部依赖
- `myrm_agent_harness.toolkits.file_parsers`：PDF/Docx/Excel/Pptx 解析
- `myrm_agent_harness.infra.atomic_write`：`text_edit_io` 的原子替换

### 被依赖方
- `app/api/files/revert.py`：revert HTTP API hydrate/cleanup + Agent restore_inbox 通知
- `app/api/files/local_actions.py`：Local reveal/open（via `reveal_utils`）
- `app/api/wiki/router.py`：`POST /wiki/vault/reveal` · `POST /wiki/vault/open-obsidian`（via `reveal_utils`）
- `app/api/files/organize.py`：workspace organize HITL apply/rollback/latest-job
- `app/api/files/workspace_text.py`：文本编辑读取/保存/另存副本（via `text_edit_io`）
- `app/core/channel_bridge/turn_handler.py`：channel /undo·/retry 文件 revert cleanup + Agent restore_inbox 通知
- `app/services/kanban/task_runner.py`：任务附件上下文注入
- `app/channels/media/document_enrichment.py`：渠道入站文档提取
