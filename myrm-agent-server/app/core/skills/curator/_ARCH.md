# app/core/skills/curator 子包架构


---

## 架构概述

技能生命周期治理（Curator）子域。提供技能清理（sweep）、配置、历史查询与后台任务编排的业务服务，以及技能合并（umbrella merge）集成能力。`get_stats_collector()` 注入 Harness `usage_recorder` 统计技能用量。属于 Server 业务层，复用 Harness 框架的技能生命周期通用能力。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 子域聚合出口：导出 sweep/配置/历史/后台任务与合并相关公共 API。 |
| `service.py` | Curator 业务服务：`run_curator_sweep`/`update_curator_config`/`get_curator_history`/`get_stats_collector`/`resolve_skill_path`，`start/stop_curator_background_task` 后台任务编排。 |
| `consolidation.py` | 技能合并（umbrella merge）集成：`run_consolidation_preview`/`run_consolidation_execute`，agent refs 重写，与 sweep 共享锁。 |

---

## 依赖关系

**被依赖**：
- `app/api/skills/` — 技能 API
