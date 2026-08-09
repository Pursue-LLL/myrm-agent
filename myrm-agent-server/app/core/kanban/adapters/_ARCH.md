# core/kanban/adapters/

## 架构概述

看板 `KanbanStore` 协议的 SQLAlchemy 实现：boards / tasks / runs / events / DAG 依赖边的 CRUD。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包导出 | — |
| `sqlalchemy_mapping.py` | 核心 | ORM ↔ 领域对象双向映射（含 board settings、task workspace/branch、attachment_ids、goal_mode/goal_max_turns） | — |
| `sqlalchemy_store.py` | 核心 | `KanbanStore`：Board/Task/Run/Event/Edge CRUD、`transition_task_status` 原子 CAS（单条 UPDATE + expected_status 守卫）、board scope（`project_id/milestone_id`）写入与 project 过滤、claim、heartbeat、zombie、Boot Recovery、批量统计 | — |

## 依赖

- `myrm_agent_harness.toolkits.kanban.types` — 看板领域类型
- `app.database.models` — Kanban ORM 表
