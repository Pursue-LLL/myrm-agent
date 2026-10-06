# api/events/

## 架构概述

SSE 事件流 HTTP 层（仅 local 模式注册）。上级文档：[../_ARCH.md](../_ARCH.md)。

此处仅提供实时通知与权限审批，不承载 agent 历史事件查询（agent 事件回放以 harness JSONL event-log 为准）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 聚合 notifications + permissions 子路由 | ✅ |
| `notifications.py` | 模块 | SSE endpoint for real-time system notifications. | ✅ |
| `permissions.py` | 模块 | Permission Management API (local mode only). | ✅ |
