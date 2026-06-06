# api/batch_optimization 模块架构


## 架构概述

批量 Skill 优化 API。创建任务前强制 `create_batch_snapshot`；WebUI `batch-optimization` 页提供提交确认、运行中/排队中「取消并回滚」（`cleanup_strategy=rollback`）与详情页 terminal 回滚。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 路由导出 | — |
| `router.py` | 核心 | 批量优化 REST（创建前 `create_batch_snapshot`；`cancel` 调 harness `cancel_batch_optimization` + `await_batch_optimization`（超时则跳过 rollback 并返 `error_message`）后再 rollback；`cancel`+`rollback` 均返 `rolled_back`/`failed`/`total_skills`/`error_message`；写盘经 `restore_skill_snapshot`） | ✅ |

## 测试

`tests/conftest.py` 启动时自动将 monorepo `myrm-agent-harness/src` 置于 `PYTHONPATH` 前（避免 `.venv` 内旧版包导致 import 失败）。直接运行：

```bash
uv run pytest tests/api/batch_optimization/ tests/services/skill_optimization/ -v
```

| 文件 | 职责 |
|------|------|
| `support.py` | 共享 `FakeBatchTask` / Repository stub |
| `conftest.py` | `batch_app` / `batch_client` fixture |
| `test_cancel_rollback.py` | `RollbackService` 全量/部分失败编排；HTTP cancel `keep` 契约；scheduler 接线；await 超时跳过 rollback |
| `test_cancel_rollback_http_integration.py` | 真 sqlite + 真 `RollbackService` + HTTP cancel 单/多 skill 写盘 + partial 契约；`create_batch_snapshot` 入库 |
| `test_skill_version_integration.py`（services 目录） | `restore_skill_snapshot` 双分支真写盘 |
