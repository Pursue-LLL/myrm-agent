# api/projects/

## 架构概述

项目 CRUD、会话归属和里程碑管理 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 项目 API 模块 | ✅ |
| `router.py` | 路由 | 项目管理 API 路由。提供项目增删改查和会话归属管理端点。 | ✅ |
| `test_fixtures.py` | 路由 | Local-only 项目锁 seed 端点：`POST /projects/test/seed-turn-lock`（创建 project + 绑定 chat + 可选确定性占用项目锁：`hold_ms=None` 不占锁 / `0` 持有到 `POST /projects/test/release-turn-lock` 显式释放 / `>0` 自动释放）、`GET /projects/test/turn-lock-status?project_id=`（只读查询锁是否持有，供 E2E 在真实 UI send 前做确定性守卫断言）。供 Chrome E2E 验证 `waiting_for_turn` 等待提示真实链路，不依赖真实并发时序与 attach 延迟）。 | ✅ |
| `milestone_router.py` | 路由 | 里程碑管理 API 路由。提供里程碑 CRUD、进度查询、路线图摘要与评估工件导入端点；导入错误在标准错误结构 `error.details` 中输出 `import_reason` 机器可读标识（如 `artifact_version_already_imported`、`no_actionable_tasks`、`no_importable_tasks`、`artifact_not_found`），并映射 409/422/404。 | ✅ |
