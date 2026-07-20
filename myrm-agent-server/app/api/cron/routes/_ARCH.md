# api/cron/routes/

## 架构概述

Cron 分域路由注册。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Cron job REST endpoints. | ✅ |
| `heartbeat.py` | 模块 | Heartbeat REST endpoints. | ✅ |
| `helpers.py` | 模块 | helpers 模块实现 | — |
| `jobs.py` | 模块 | Cron job CRUD REST endpoints. `GET /` 支持 `chat_id` 过滤绑定会话。 | ✅ |
| `push_messages.py` | 模块 | Poll for recent cron push notifications (local single-user mode). | ✅ |
| `runs.py` | 模块 | Cron run history REST endpoints. | ✅ |
| `stats.py` | 模块 | Cron usage statistics REST endpoint. | ✅ |
| `scheduler_health.py` | 模块 | Scheduler liveness endpoint (green/yellow/red). Delegates to harness CronScheduler.health(). | ✅ |
| `blueprints.py` | 模块 | `GET/POST /blueprints` — 五语系（en/zh/ja/de/ko）蓝图目录与 fill；委托 `core.cron.blueprints` SSOT | ✅ |
| `triggers.py` | 模块 | Cron trigger dispatch and integrity verification REST endpoints | ✅ |
