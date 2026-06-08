# api/background_tasks/

## 架构概述

本目录模块说明。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Background tasks API — manage /background (/btw /bg) session tasks. | ✅ |
| `router.py` | 路由 | REST API layer for background task management. Exposes in-memory task state from ChannelBackgroundTaskHandler to the frontend via standard HTTP endpoints. """ | ✅ |
