# canvas/ 服务架构

## 架构概述

Agent-facing canvas operations and shared filesystem utilities.
Provides read/write access to tldraw canvas state for internal agent tools
and external MCP tool endpoints.

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 模块导出 | ✅ |
| `_paths.py` | 核心 | 共享文件系统路径工具：UUID 校验、路径构建、常量 | ✅ |
| `operations.py` | 核心 | Canvas state read、selection read、element insertion | ✅ |

## 依赖

无外部跨层依赖。SSE 通知由 api 层（调用方）负责触发。
