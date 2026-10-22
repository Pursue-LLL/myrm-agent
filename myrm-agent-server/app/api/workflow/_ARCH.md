# api/workflow/ 架构说明

## 架构概述

多步骤工作流全景执行轨迹可视化、节点级快照审计与断点重放 API 路由层。
提供五阶执行全景节点快照查询与基于前序节点缓存快照的断点重放自愈端点。

## 核心文件

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 模块门面与路由导出 | ✅ |
| `trace_router.py` | 路由 | 提供 `GET /workflow/{id}/trace` 与 `POST /workflow/replay-from-node` | ✅ |

## 依赖关系

- 模式层：`app.schemas.workflow_trace`
- 服务层：`app.services.workflow.trace_service`
- 上级路由：`app.api.router`
