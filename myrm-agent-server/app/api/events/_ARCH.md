# api/events/

## 架构概述

SSE 事件流 HTTP 层（仅 local 模式注册）。上级文档：[../_ARCH.md](../_ARCH.md)。

此处仅提供实时通知与权限审批，不承载 agent 历史事件查询（agent 事件回放以 harness JSONL event-log 为准）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 聚合 notifications 子路由 | ✅ |
| `notifications.py` | 模块 | SSE endpoint for real-time system notifications；载荷按 `default=str` 序列化（与 `PubSubBus.publish` 的去重键同一兜底），总线接受的事件都能写出，积压回放不会让重连反复失败 | ✅ |
