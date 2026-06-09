# api/tasks/

## 架构概述

通用异步任务队列 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Task API module. | ✅ |
| `router.py` | 路由 | Task management API routes. | ✅ |
