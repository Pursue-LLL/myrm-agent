# api/cron/routes/

## 架构概述

Cron 分域路由注册。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Cron job REST endpoints. | ✅ |
| `actions.py` | 模块 | Cron 任务生命周期动作端点（duplicate/pause/resume/trigger/test-delivery/reset-baseline）；`trigger` 起一次手动试跑：已启动 202，任务已在运行 409，不存在或未启用 404，拒绝时任务保持原样；`test-delivery` 把一次性载荷送进真实投递链路（`ChannelResultDelivery`）：不带请求体测已保存的投递，带 `delivery` 或 `failure_delivery` 测未保存的配置，任务不存在 404，渠道无需外发（`NON_OUTBOUND_CHANNELS`：chat/silent/none）400，投递失败 502；测试不改任务，投递成败都一样，任务的状态、连续失败次数与最近错误保持原样（`tests/api/cron/test_cron_delivery_secret.py`） | ✅ |
| `blueprints.py` | 模块 | `GET/POST /blueprints` — 中英双语（en/zh）蓝图目录与 fill；委托 `core.cron.blueprints` SSOT | ✅ |
| `delivery_health.py` | 模块 | `GET /{job_id}/delivery-health` — 任务当前投递目的地（渠道 + 地址）的健康度：状态、连续失败数、最近一次失败的类别与时间（UTC），固定看最近 24 小时；任务不存在 404，目的地没有结论（无需外发的渠道，或窗口内没有投递记录）时 204 且没有响应体（前端的请求函数读不了 JSON `null` 体，会在读取时抛错，而 204 正是它按「无内容」处理的答复；`tests/api/cron/test_delivery_health_api.py`） | ✅ |
| `heartbeat.py` | 模块 | Heartbeat REST endpoints. Supports `agent_id` binding for Agent Profile inheritance; the enable prompt passes the risk gate (`reject_if_risky`) before it is stored; the status carries `paused_reason`, the reason the scheduler switched the heartbeat off by itself (none when the user did). | ✅ |
| `helpers.py` | 模块 | Cron 响应映射（`paused_reason` 随任务响应带出，字段对齐由 `tests/architecture/test_cron_route_field_parity.py` 守住）；`_delivery_from_request` 把投递请求转成配置，除无需外发的渠道（`NON_OUTBOUND_CHANNELS`）外必须带目标地址；`workflow_template_display_name` 与 execution gate 同规则 enrich；`_check_allowed_roots` 把 `allowed_roots` 逐个过工作区路径闸门（`ensure_root_grantable`，拒绝时 400 + `ErrorDetail(field=allowed_roots, issue)`；根按用户输入原样保存，`~/Documents` 这类芯片仍能对上） | — |
| `jobs.py` | 模块 | Cron job CRUD REST endpoints. `GET /` 支持 `chat_id` 过滤，只列用户任务与其总数（心跳这类系统任务不在其中，只在设置页的心跳接口里出现）；create/PATCH 校验 `allowed_roots`（`_check_allowed_roots`）；create/update/PATCH 校验 DW 模板绑定（`workflow_templates/validation.py`）；webhook delivery secret 创建生成/更新保留；create/PATCH 的 `prompt` 先过风险闸门（`reject_if_risky`，命中 400 `risk_held`，原文不落库；PATCH 未带 `prompt` 时不重新过闸，`shell` 任务的 `command` 是被执行的命令，不过闸） | ✅ |
| `prerequisite.py` | 模块 | `POST /prerequisite-check` — 定时任务创建前手动成功验证门禁统计查询端点 | ✅ |
| `runs.py` | 模块 | Cron run history REST endpoints. 全局运行历史按任务 id 取任务名时带 `include_system=True`，心跳的运行才有名字（前端 `useJobDisplayName` 把保留存储名换成用户认识的标题）。 | ✅ |
| `stats.py` | 模块 | Cron usage statistics REST endpoint. | ✅ |
| `scheduler_health.py` | 模块 | Scheduler liveness endpoint (green/yellow/red). Delegates to harness CronScheduler.health(). | ✅ |
| `triggers.py` | 模块 | Cron trigger dispatch REST endpoints | ✅ |
