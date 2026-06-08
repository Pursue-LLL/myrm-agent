# api/health/

## 架构概述

本目录模块说明。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `benchmark.py` | 模块 | Provides asynchronous performance benchmark execution and SSE streaming. """ | ✅ |
| `diagnostic.py` | 模块 | Returns the current hardened diagnostic state of the agent engine. | ✅ |
| `memory.py` | 模块 | Memory diagnostics API. Provides observability for memory leaks and OOM prevention. """ | ✅ |
| `router.py` | 路由 | HTTP 路由处理器 | — |
