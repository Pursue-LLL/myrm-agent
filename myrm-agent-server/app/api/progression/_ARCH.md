# api/progression/ 模块架构

## 架构概述

用户能力进度 HTTP 层，提供读取当前等级/里程碑状态与标记里程碑完成的接口。
业务持久化与等级计算在 [app/services/progression/_ARCH.md](../../services/progression/_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `__init__.py` | 入口 | Progression API exports | ✅ |
| `router.py` | 路由 | `GET /api/v1/progression`、`PATCH /api/v1/progression/{milestone_id}` | ✅ |

## 模块依赖

- `app.services.progression.service` — 进度读取、里程碑打点、等级计算
- `app.services.progression.schema` — 里程碑定义
