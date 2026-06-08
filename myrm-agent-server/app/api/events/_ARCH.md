# api/events/

## 架构概述

本目录模块说明。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Agent Events API | ✅ |
| `notifications.py` | 模块 | SSE endpoint for real-time system notifications. | ✅ |
| `permissions.py` | 模块 | Permission Management API (local mode only). | ✅ |
| `router.py` | 路由 | Agent Events API Router | ✅ |
