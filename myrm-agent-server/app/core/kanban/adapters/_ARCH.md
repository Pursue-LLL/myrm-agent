# core/kanban/adapters/

## 架构概述

看板 `KanbanStore` 协议的 SQLAlchemy 实现：boards / tasks / runs / events / DAG 依赖边的 CRUD。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包导出 | — |
| `sqlalchemy_mapping.py` | 核心 | ORM ↔ 领域对象双向映射（含 board settings、task workspace/branch、attachment_ids、goal_mode/goal_max_turns）；`stored_block_details` / `status_change_values`：阻塞的原因、类型与到点时间只对阻塞态任务落库——写整个任务对象的路径（建行、更新行）走前者，只改状态的 UPDATE（`transition_task_status`）用后者，任务经移动、智能体取消、计划移除、状态 CAS 等任何路径离开阻塞列都不会留下这三项（计划移除直接改行，在 `sqlalchemy_store/` 里单独清）；新增只改状态的 UPDATE 同样要用 `status_change_values` | — |
| `sqlalchemy_store/` | 核心 | `KanbanStore` 的 SQLAlchemy 实现，按实体拆 7 个 mixin（boards / tasks / dependencies / plan / execution / runs / events）+ `common`（值类型与 rowcount helper）+ `store`（组合，无实例状态）：Board/Task/Run/Event/Edge CRUD、`transition_task_status` 原子 CAS、board scope、claim、heartbeat、zombie、Boot Recovery、`earliest_scheduled_until`、批量统计。见 [sqlalchemy_store/_ARCH.md](sqlalchemy_store/_ARCH.md) | — |

## 依赖

- `myrm_agent_harness.toolkits.kanban.types` — 看板领域类型
- `app.database.models` — Kanban ORM 表
