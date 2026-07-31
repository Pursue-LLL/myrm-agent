# services/compounding_playbook/ 模块架构

## 架构概述

Settings「复利闭环」checklist 的轻量聚合服务。统计 memory / skills / cron / verify 四行就绪状态与计数。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `__init__.py` | 入口 | Service exports | ✅ |
| `status_service.py` | 核心 | `build_compounding_status` 四行 checklist 快照 | ✅ |

## 模块依赖

- `myrm_agent_harness.toolkits.memory.MemoryManager` — PROFILE/SEMANTIC/CLAIM 计数
- `myrm_agent_harness.toolkits.cron.manager.CronManager` — 任务与 acceptance 计数
- `app.core.skills.store.service.skills_service` — 活跃技能计数（无 agent 绑定时）
- `app.database.models.agent.Agent` — 可选 agent_id 技能绑定计数
