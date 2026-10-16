# app/core/skills/curator 子包架构


---

## 架构概述

技能生命周期治理（Curator）子域。提供技能清理（sweep）、配置、历史查询与后台任务编排的业务服务，以及技能合并（umbrella merge）集成能力。`get_stats_collector()` 注入 Harness `usage_recorder` 统计技能用量。属于 Server 业务层，复用 Harness 框架的技能生命周期通用能力。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 子域聚合出口：导出 sweep/配置/历史/后台任务与合并相关公共 API。 |
| `service.py` | Curator 业务服务：`run_curator_sweep`/`update_curator_config`（合并后的数值越界时抛 `ValueError`，缓存与落盘保持不变，`PATCH /curator/config` 映射为 422；已落盘的越界配置在读取时回退为默认阈值、总开关保留）/`get_curator_history`/`get_stats_collector`/`resolve_skill_path`/`set_skill_archived`（用户归档/恢复唯一入口，含 pinned 守卫）/`describe_skill_lifecycle`/`get_skill_diagnostics`（每条发现带 `bound`：技能被 Agent 档案或未结束的 cron 任务绑定，界面据此不提供归档；没有发现时不查库）/`remediate_skill_finding`，`start/stop_curator_background_task` 后台任务编排；`apply_skill_archived` 是归档/恢复的唯一写入口（手动归档、恢复、修复、成长时间线共用），写入后 `bump_skill_config_version()`，让缓存了旧技能目录的热会话下一轮重建，而不是继续带着已归档的技能；后台/手动 sweep 只要归档了技能（`archived_count > 0`）同样 bump。 |
| `bound_skills.py` | `bound_skill_names`：找出被 Agent 档案（`skill_ids`/`mounted_skill_ids`/`command_bindings`）或未完成 cron 任务（`skill_ids`）绑定的技能；sweep 与合并将其作为 `protected_names` 交给 Harness Curator，永不被淘汰/归档/合并。查询失败则中止本次治理（不在不知道绑定关系时归档）。 |
| `local_skills.py` | `scan_local_skills` → `LocalSkillScan(skills, installed_names)`：sweep、合并（预览/执行）、健康探针、技能医生（`get_skill_diagnostics`）共用的唯一技能扫描入口，每次调用各自重新扫描。`installed_names` = 带市场 `origin.json` 的技能 ∪ 位于非主目录（`DEFAULT_LOCAL_SKILL_PATHS` 第 0 项以外，即 Cursor/Claude/Codex 等其他工具的目录）的技能；仅当 `protect_installed_skills` 开启时由引擎当作豁免名单（与 `protected_names` 同构，按名称匹配）。 |
| `consolidation.py` | 技能合并（umbrella merge）集成：`run_consolidation_preview`/`run_consolidation_execute`，agent refs 重写，与 sweep 共享锁。 |

---

## 依赖关系

**被依赖**：
- `app/api/skills/` — 技能 API
