# api/cron/routes/

## 架构概述

本目录模块说明。上级文档：[../../../_ARCH.md](../../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Cron job REST endpoints. | ✅ |
| `heartbeat.py` | 模块 | Heartbeat REST endpoints. | ✅ |
| `helpers.py` | 模块 | helpers 模块实现 | — |
| `jobs.py` | 模块 | Cron job CRUD REST endpoints. | ✅ |
| `push_messages.py` | 模块 | Poll for recent cron push notifications (local single-user mode). | ✅ |
| `runs.py` | 模块 | Cron run history REST endpoints. | ✅ |
| `stats.py` | 模块 | Cron usage statistics REST endpoint. | ✅ |
| `triggers.py` | 模块 | Cron trigger dispatch and integrity verification REST endpoints """ | ✅ |
