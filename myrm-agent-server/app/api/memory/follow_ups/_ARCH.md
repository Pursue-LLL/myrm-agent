# api/memory/follow_ups/

## 架构概述

Proactive follow-up REST API（路由前缀 `/memory/follow-ups`）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Follow-up tracking API endpoints. | ✅ |
| `router.py` | 路由 | List / dismiss / snooze follow-up items. | ✅ |
