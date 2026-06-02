# api/checkpoint 模块架构


## 架构概述

Checkpoint 和文件快照管理 API。提供 Subagent checkpoint 的列表、恢复、删除、清理接口，以及文件快照的列表、恢复、对比、删除、清理接口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 路由导出 | — |
| `router.py` | 核心 | Checkpoint + File Snapshot REST 接口 | ✅ |

## API 端点

### Checkpoint 端点
- `GET /checkpoint/list` — 列出所有检查点
- `POST /checkpoint/resume` — 从检查点恢复（返回 checkpoint_data）
- `DELETE /checkpoint/{task_id}` — 删除检查点
- `POST /checkpoint/cleanup` — 清理过期检查点

### File Snapshot 端点
- `GET /checkpoint/file-snapshot/list` — 列出文件快照
- `POST /checkpoint/file-snapshot/restore` — 恢复文件快照
- `GET /checkpoint/file-snapshot/{snapshot_id}/diff` — 对比快照与当前状态
- `DELETE /checkpoint/file-snapshot/{snapshot_id}` — 删除文件快照
- `POST /checkpoint/file-snapshot/cleanup` — 清理旧快照
