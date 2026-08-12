# api/checkpoint/

## 架构概述

LangGraph checkpoint 管理 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

文件快照读写统一走 harness `create_file_snapshot_store()`（git 环境→ShadowGit bare repo、无 git→LocalFile fallback），与 `SnapshotInterceptor` 同源，避免"写 shadow git、读 local"断链。`POST /file-snapshot/create` 以 `SnapshotTrigger.MANUAL` 创建用户手动版本点（快照面板「创建版本」入口）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Checkpoint management API package. | ✅ |
| `schemas.py` | 模型 | Pydantic request/response schemas for checkpoint & file snapshot APIs. | ✅ |
| `router.py` | 路由 | Checkpoint and file snapshot management REST API（含 file-snapshot 手动 create/restore/diff/delete/cleanup/list）。 | ✅ |
| `_snapshot_notify.py` | 辅助 | Agent rollback notification via restore_inbox（恢复后通知 Agent 上下文变化）。 | ✅ |
