# api/batch_directory/

## 架构概述

批量目录并行 Prompt 批次 HTTP 层：创建/列表/详情/取消/删除。业务编排见 [services/batch_directory/_ARCH.md](../../services/batch_directory/_ARCH.md)。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 `router` | — |
| `router.py` | 路由 | `/api/v1/batch-directories` 端点（POST `/`、GET `/`、GET `/{id}`、POST `/{id}/cancel`、DELETE `/{id}`） | ✅ |
| `schemas.py` | 模块 | Pydantic 模型：`BatchProjectCreate`/`BatchProjectResponse`/`BatchProjectDetailResponse`/`BatchProjectListResponse`/`BatchTaskItem` | — |

## 挂载（`app/api/router.py`）

- `batch_directory_router` → `/api/v1` + `/batch-directories` 前缀
