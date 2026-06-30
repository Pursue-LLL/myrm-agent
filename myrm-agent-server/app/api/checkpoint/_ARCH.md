# api/checkpoint/

## 架构概述

LangGraph checkpoint 管理 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Checkpoint management API package. | ✅ |
| `schemas.py` | 模型 | Pydantic request/response schemas for checkpoint & file snapshot APIs. | ✅ |
| `router.py` | 路由 | Checkpoint and file snapshot management REST API. | ✅ |
| `_snapshot_notify.py` | 辅助 | SSE restore event emission and Agent rollback notification. | ✅ |
