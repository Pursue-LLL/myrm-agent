# api/goals/

## 架构概述

长时 Goal 编排 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Goal API exports. | ✅ |
| `router.py` | 路由 | Provides HTTP endpoints for the frontend to pause, resume, and clear goals | ✅ |
