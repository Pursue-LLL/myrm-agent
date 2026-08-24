# api/cron/routes/

## 架构概述

Cron 分域路由注册。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Cron job REST endpoints. | ✅ |
| `actions.py` | 模块 | Cron 任务生命周期动作端点（duplicate/pause/resume/trigger/test-delivery/reset-baseline） | ✅ |
| `heartbeat.py` | 模块 | Heartbeat REST endpoints. Supports `agent_id` binding for Agent Profile inheritance. | ✅ |
| `helpers.py` | 模块 | Cron 响应映射；`workflow_template_display_name` 与 execution gate 同规则 enrich | — |
| `jobs.py` | 模块 | Cron job CRUD REST endpoints. `GET /` 支持 `chat_id` 过滤；create/update/PATCH 校验 DW 模板绑定（`workflow_templates/validation.py`）；webhook delivery secret 创建生成/更新保留；`POST /{job_id}/test-delivery` 复用投递链路做一键测试 | ✅ |
| `prerequisite.py` | 模块 | `POST /prerequisite-check` — 定时任务创建前手动成功验证门禁统计查询端点 | ✅ |
| `push_messages.py` | 模块 | Poll for recent cron push notifications (local single-user mode). | ✅ |
| `runs.py` | 模块 | Cron run history REST endpoints. | ✅ |
| `stats.py` | 模块 | Cron usage statistics REST endpoint. | ✅ |
| `scheduler_health.py` | 模块 | Scheduler liveness endpoint (green/yellow/red). Delegates to harness CronScheduler.health(). | ✅ |
| `blueprints.py` | 模块 | `GET/POST /blueprints` — 五语系（en/zh/ja/de/ko）蓝图目录与 fill；委托 `core.cron.blueprints` SSOT | ✅ |
| `triggers.py` | 模块 | Cron trigger dispatch and integrity verification REST endpoints | ✅ |
