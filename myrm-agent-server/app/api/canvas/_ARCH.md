# canvas/ API 模块架构

## 架构概述

Infinite canvas workspace REST API. Provides CRUD for canvas metadata,
tldraw snapshot persistence, selection state read/write, and SSE-based
real-time change notifications for Agent ↔ frontend synchronization.

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 模块入口，导出 router | ✅ |
| `router.py` | 核心 | CRUD、snapshot、selection、SSE 端点 | ✅ |

## 数据模型

Canvas metadata in SQLite (`app.database.models.canvas::Canvas`).
tldraw snapshots stored as JSON files under `~/.myrm/canvas/{canvas_id}/`.

## 依赖

- `app.database.models.canvas::Canvas` — SQLite ORM 模型
- `app.database.connection::get_db` — 异步 session provider
- `app.services.canvas._paths` — 共享文件系统路径工具（正向依赖 services 层）
- `app.services.canvas._events` — SSE 事件通知中枢（正向依赖 services 层）
- `asyncio.to_thread` — 文件 I/O offload 到线程池（零外部依赖）
