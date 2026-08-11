# api/batch_directory/

## 架构概述

批量目录并行 Prompt 批次 HTTP 层：创建/列表/详情/取消/重试/重跑/删除。业务编排见 [services/batch_directory/_ARCH.md](../../services/batch_directory/_ARCH.md)。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 `router` | — |
| `router.py` | 路由 | `/api/v1/batch-directories` 端点（POST `/`、GET `/`、GET `/{id}`、POST `/{id}/cancel`、POST `/{id}/retry`、POST `/{id}/rerun`、POST `/{id}/tasks/{task_id}/retry`、DELETE `/{id}`）；`ValueError` 映射为 400 | ✅ |
| `schemas.py` | 模块 | Pydantic 模型：`BatchProjectCreate`/`BatchProjectResponse`（含 `failed_directories`/`missing_artifact_directories`）/`BatchProjectDetailResponse`（含 `created_task_ids`/`cancelled_task_ids`/`retried_task_ids`/`retry_failed_directories`/`rerun_task_ids`/`rerun_failed_directories`）/`BatchProjectListResponse`/`BatchTaskItem`（含 `artifact_status`） | — |

## 挂载（`app/api/router.py`）

- `batch_directory_router` → `/api/v1` + `/batch-directories` 前缀
