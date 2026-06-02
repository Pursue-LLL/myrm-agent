# api/cron 模块架构


---

## 架构概述

定时任务 REST API 层。定义 Pydantic 请求/响应模型和 FastAPI 路由，
委托框架层 `CronManager` 处理业务逻辑，不再直接操作数据库会话。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `schemas.py` | 核心 | Pydantic 请求/响应模型（CronJob CRUD、MonitorConfig、Schedule、Delivery、Trigger 等），提供字段校验。包含 `EventTriggerDispatchRequest` / `SystemEventTriggerDispatchRequest` dispatch 请求体模型 | INPUT: `myrm_agent_harness.toolkits.cron.types`; OUTPUT: API 请求/响应模型 |
| `routes/__init__.py` | 核心 | 路由聚合，将各子路由挂载到 cron APIRouter | INPUT: routes/*; OUTPUT: 聚合路由 |
| `routes/helpers.py` | 核心 | Manager/Scheduler 获取 + 领域对象与 schema 转换工具函数 | INPUT: harness types, schemas; OUTPUT: 转换工具 |
| `routes/jobs.py` | 核心 | Job CRUD（list/create/get/update/delete/pause/resume/trigger/reset-baseline）9 个端点 | INPUT: helpers; OUTPUT: HTTP 响应 |
| `routes/heartbeat.py` | 核心 | Heartbeat（status/enable/disable）3 个端点，支持 interval 和 cron 调度模式 | INPUT: helpers, harness heartbeat, parser; OUTPUT: HTTP 响应 |
| `routes/runs.py` | 核心 | 执行记录查询（job runs / all runs）2 个端点 | INPUT: helpers; OUTPUT: HTTP 响应 |
| `routes/stats.py` | 核心 | Token 用量统计 1 个端点 | INPUT: sqlalchemy_aggregation; OUTPUT: HTTP 响应 |
| `routes/triggers.py` | 核心 | Trigger dispatch（event/system-event/webhook）+ integrity verify 4 个端点 | INPUT: helpers, harness integrity; OUTPUT: HTTP 响应 |
| `routes/push_messages.py` | 核心 | 推送消息轮询 1 个端点 | INPUT: push_store; OUTPUT: HTTP 响应 |

---

## 依赖关系

### 内部依赖

- `myrm_agent_harness.toolkits.cron`：领域类型 + CronJobPatch
- `app.core.cron.adapters.setup`：获取 CronManager 单例
- `app.core.cron.push_store`：推送消息内存队列
- `app.api.dependencies`：用户鉴权

### 被依赖

- `app.api.router`：注册到主路由 `/cron`
