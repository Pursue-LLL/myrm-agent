# core/kanban/adapters/

## 架构概述

看板 `KanbanStore` 协议的 SQLAlchemy 实现：boards / tasks / runs / events / DAG 依赖边的 CRUD。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包导出 | — |
| `sqlalchemy_mapping.py` | 核心 | ORM ↔ 领域对象双向映射（含 board settings、task workspace/branch、attachment_ids、goal_mode/goal_max_turns）；`stored_block_details` / `status_change_values`：阻塞的原因、类型与到点时间只对阻塞态任务落库——写整个任务对象的路径（建行、更新行）走前者，只改状态的 UPDATE（`transition_task_status`）用后者，任务经移动、智能体取消、计划移除、状态 CAS 等任何路径离开阻塞列都不会留下这三项（计划移除直接改行，在 `sqlalchemy_store.py` 里单独清）；新增只改状态的 UPDATE 同样要用 `status_change_values` | — |
| `sqlalchemy_store.py` | 核心 | `KanbanStore`：Board/Task/Run/Event/Edge CRUD、`transition_task_status` 原子 CAS（单条 UPDATE + expected_status 守卫）、board scope（`project_id/milestone_id`）写入与 project 过滤、claim、heartbeat、zombie、Boot Recovery、`earliest_scheduled_until`（沙箱到点唤醒用：所有看板 `SCHEDULED` 阻塞任务严格晚于给定时刻的最早解除时间）、批量统计 | — |

## 依赖

- `myrm_agent_harness.toolkits.kanban.types` — 看板领域类型
- `app.database.models` — Kanban ORM 表
