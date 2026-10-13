# app/core/skills/curator 子包架构


---

## 架构概述

技能生命周期治理（Curator）子域。提供技能清理（sweep）、配置、历史查询与后台任务编排的业务服务，以及技能合并（umbrella merge）集成能力。`get_stats_collector()` 注入 Harness `usage_recorder` 统计技能用量。属于 Server 业务层，复用 Harness 框架的技能生命周期通用能力。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 子域聚合出口：导出 sweep/配置/历史/后台任务与合并相关公共 API。 |
| `service.py` | Curator 业务服务：`run_curator_sweep`/`update_curator_config`/`get_curator_history`/`get_stats_collector`/`resolve_skill_path`/`set_skill_archived`（用户归档/恢复唯一入口，含 pinned 守卫）/`describe_skill_lifecycle`/`get_skill_diagnostics`/`remediate_skill_finding`，`start/stop_curator_background_task` 后台任务编排。 |
| `bound_skills.py` | `bound_skill_names`：找出被 Agent 档案（`skill_ids`/`mounted_skill_ids`/`command_bindings`）或未完成 cron 任务（`skill_ids`）绑定的技能；sweep 与合并将其作为 `protected_names` 交给 Harness Curator，永不被淘汰/归档/合并。查询失败则中止本次治理（不在不知道绑定关系时归档）。 |
| `consolidation.py` | 技能合并（umbrella merge）集成：`run_consolidation_preview`/`run_consolidation_execute`，agent refs 重写，与 sweep 共享锁。 |

---

## 依赖关系

**被依赖**：
- `app/api/skills/` — 技能 API
