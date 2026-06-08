# api/memory/

## 架构概述

本目录模块说明。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Memory API module | ✅ |
| `router.py` | 路由 | Memory API router | ✅ |
| `shared_context_schemas.py` | 模块 | 共享上下文 API Schema 层。集中定义 Shared Context 产品接口的数据契约。 """ | ✅ |
| `utils.py` | 模块 | Memory API utilities — re-exports shared service-layer helpers for route modules. | ✅ |
