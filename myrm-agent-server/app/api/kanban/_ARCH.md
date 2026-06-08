# api/kanban/

## 架构概述

本目录模块说明。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Kanban API routes — boards, tasks, SSE events. """ | ✅ |
| `http_common.py` | 模块 | Kanban API 共享路由与 DTO 装配；`routes/*` 仅注册端点。 """ | ✅ |
| `pipeline_router.py` | 模块 | Pipeline template REST API endpoints for Kanban. """ | ✅ |
| `router.py` | 路由 | Kanban API 聚合入口，供 app.api.router 注册。 """ | ✅ |
| `schemas.py` | 模块 | Pydantic models for kanban API endpoints. """ | ✅ |
