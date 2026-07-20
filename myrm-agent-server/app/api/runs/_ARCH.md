# api/runs/ 模块架构

## 架构概述

Unified Runs Hub 聚合 API。只读端点，将 Cron Runs、Kanban Background Tasks、Shell Background Tasks 合并为统一时间线视图。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包导出 | — |
| `router.py` | 核心 | GET /runs 聚合端点 | ✅ |
| `schemas.py` | 模型 | UnifiedRunResponse/UnifiedRunsListResponse | — |

## 端点明细（`/api/v1/runs`）

| 方法 | 路径 | 查询参数 | 说明 |
|------|------|----------|------|
| GET | `/runs` | `source`, `status`, `limit`, `offset` | 聚合全源运行记录；响应含 `degraded` / `failed_sources` |

## 数据源

1. **Cron Runs** — 通过 `CronManager.list_runs()` 查询
2. **Kanban Background Tasks** — 查询 `__background_tasks__` board 中的任务
3. **Shell Background Tasks** — 通过 `list_shell_background_tasks()` 获取内存中任务

## 约束

- 只读：无写操作
- 并行查询：各源独立 collect；异常或子系统不可用记入 `failed_sources`
- 字段：`has_execution_steps` = cron metadata 含 progressSteps
- 字段：`stop_reason` = 统一结构化停止原因（优先读取 `metadata.stopReason`，其次回退 `progressSteps`/error 推断）
- `failed_sources`：子系统不可用或 fetch 异常；Kanban 尚无 system board 视为空列表（非 degraded）
- Kanban `failed`/`blocked` 任务：error 含 `timed out` → `timed_out`；含 `cancelled` → `cancelled`（与 channel bridge 一致）
- 分页：各源最多拉取 `limit + offset + 10` 条后内存合并；`total`/`has_more` 在超 cap 历史下可能偏小
- 无新 DB 表：复用现有 `cron_runs`、Kanban task store
