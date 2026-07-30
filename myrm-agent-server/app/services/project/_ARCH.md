# app/services/project/ 模块架构

项目管理服务。提供项目的 CRUD 操作、会话归属管理、里程碑路线图管理以及项目级别的并发调度，支持多智能体在同一项目工作区下的协同。

## 文件清单

| 文件                  | 地位     | 职责                                         | I/O/P |
| --------------------- | -------- | -------------------------------------------- | ----- |
| project_service.py    | 核心服务 | 项目 CRUD + 会话归属移动（单个/批量）        | ✅    |
| workspace_path_resolve.py | 路径校验 | Project workspace_path 规范化与安全校验       | ✅    |
| milestone_service.py  | 核心服务 | 里程碑 CRUD + 进度统计 + 路线图摘要生成       | ✅    |
| assessment_import_service.py | 核心服务 | 评估工件导入：artifact markdown → 里程碑 + 项目作用域看板 + 任务回执 | ✅ |
| orchestrator.py       | 并发控制 | 项目级并发调度器，确保同一项目下的多 Agent 回合制执行 | ✅    |
| __init__.py           | 模块入口 | 导出 ProjectService, MilestoneService        | ✅    |

测试：`tests/services/project/test_workspace_path_resolve.py` · `tests/services/project/test_legacy_workspace_path_migration.py` · `tests/integration/test_project_workspace_bind_file_write_integration.py` · `tests/api/chats/test_effective_workspace_ssot.py`

启动迁移：`app/database/migrations.py::CLEAR_LEGACY_PROJECT_WORKSPACE_PATHS_SQL` 清空历史假路径 `/persistent/workspace/project_%`，用户需通过 Mount Wizard 重新绑定。

工作区 SSOT：`app/services/chat/effective_workspace.py` — Agent / GET chat / UI 共用同一目录解析顺序。

P1 变更感知：`app/services/workspace/file_watch_service.py` + `app/api/files/browse_watch.py` — Web/SaaS 文件树经 SSE `workspace_file_changed` 自动刷新（`useWorkspaceFiles` 注册 watch）。
