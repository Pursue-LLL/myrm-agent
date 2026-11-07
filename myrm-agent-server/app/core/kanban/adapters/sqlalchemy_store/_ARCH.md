# app/core/kanban/adapters/sqlalchemy_store 子包架构

`KanbanStore` 的 SQLAlchemy 实现。类本身**不持有实例状态**：每个方法独立 `async with get_session()`，按实体拆成 7 个 mixin，事务边界与调用顺序不变；`app.core.kanban.adapters.sqlalchemy_store` 导入路径不变。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 聚合 `SqlAlchemyKanbanStore`、`TaskCardStats`、`BoardEventRow` | — |
| `common.py` | 辅助 | `TaskCardStats` / `BoardEventRow` 值类型与 `_exec_rowcount` | — |
| `store.py` | 核心 | `SqlAlchemyKanbanStore`：七个 mixin 组合，无 `__init__`、无实例状态 | — |
| `boards.py` | 核心 | Board CRUD 与 board scope（`project_id/milestone_id`） | — |
| `tasks.py` | 核心 | Task CRUD、列表/计数、`batch_task_stats` 卡片统计、active-branch 元数据 | — |
| `dependencies.py` | 核心 | 依赖边（DAG）：DFS 环检测、加/删边、parents/children、`are_dependencies_met` | — |
| `plan.py` | 核心 | `revise_plan` 计划修订与 `clear_agent_references` | — |
| `execution.py` | 核心 | claim、`transition_task_status`（原子 CAS）、heartbeat、zombie、到点唤醒扫描、Boot Recovery | — |
| `runs.py` | 核心 | `TaskRun` 行创建/完成/列表与 run 模型转换 | — |
| `events.py` | 核心 | task/board 事件日志写入与读取 | — |

## 依赖关系

- 上游：`app.database.connection.get_session`、`app.database.models.kanban`、`app.core.kanban.adapters.sqlalchemy_mapping`、harness `toolkits.kanban.{protocols,types}`
- 下游：`app/services/kanban/**`、`app/api/kanban/**`；`app/core/kanban/adapters/__init__.py` 负责 re-export
