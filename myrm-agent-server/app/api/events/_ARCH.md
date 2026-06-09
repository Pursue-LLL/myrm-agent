# api/events/

## 架构概述

SSE 事件流 HTTP 层（仅 local 模式注册）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Agent Events API | ✅ |
| `notifications.py` | 模块 | SSE endpoint for real-time system notifications. | ✅ |
| `permissions.py` | 模块 | Permission Management API (local mode only). | ✅ |
| `router.py` | 路由 | Agent Events API Router | ✅ |
