# app/core/skills/curator 子包架构


---

## 架构概述

技能生命周期治理（Curator）子域。提供技能清理（sweep）、配置、历史查询与后台任务编排的业务服务，以及技能合并（umbrella merge）集成能力。`get_stats_collector()` 注入 Harness `usage_recorder` 统计技能用量。属于 Server 业务层，复用 Harness 框架的技能生命周期通用能力。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 子域聚合出口：导出 sweep/配置/历史/后台任务与合并相关公共 API。 |
| `service.py` | Curator 业务服务：`run_curator_sweep`/`update_curator_config`（合并后的数值越界时抛 `ValueError`，缓存与落盘保持不变，`PATCH /curator/config` 映射为 422；已落盘的越界配置在读取时回退为默认阈值、总开关保留）/`get_curator_history`/`get_stats_collector`/`resolve_skill_path`/`set_skill_archived`（恢复）/`archive_skill_with_guards`（手动归档：bound + pinned）/`describe_skill_lifecycle`/`get_skill_diagnostics`（每条发现带 `bound`：技能被 Agent 档案、未结束的 cron 任务或仍可运行的看板任务绑定，界面据此不提供归档；没有发现时不查库）/`remediate_skill_finding`，`start/stop_curator_background_task` 后台任务编排；`apply_skill_archived` 是归档/恢复的唯一写入口（手动归档、恢复、修复、成长时间线共用），写入后 `bump_skill_config_version()`，让缓存了旧技能目录的热会话下一轮重建，而不是继续带着已归档的技能。sweep 归档了技能（`archived_count > 0`）时同样 bump，并额外发布 `SKILL_POOL_UPDATED`：版本号只作用于服务端热会话，前端技能列表靠这条事件才会按新状态重刷（技能页默认隐藏已归档技能，不刷新则本轮归档的技能会停留到用户手动重载），与 install/uninstall/sync 走同一个刷新通道。历史记录同时落盘 `skipped_pinned` 与 `skipped_protected`，让"0 变化"的运行能说明有多少技能因被固定或受保护而豁免。 |
| `bound_skills.py` | `bound_skill_names` + `assert_skill_not_bound_for_archive`：Agent 档案（`skill_ids`/`mounted_skill_ids`/`command_bindings`）、未完成 cron 任务（`skill_ids`）与仍可运行看板任务（`extra_skill_ids`；已完成与已归档的不算，失败的可重试故仍算）的绑定集合；自动 sweep 与合并作 `protected_names` 豁免，手动归档入口同样拒绝仍被绑定的技能；健康探针也用它产出 `bound` 豁免理由（与 sweep 同源，避免探针把清扫不动的故障技能算作可清理），技能医生用它标记 `bound`。查询失败则中止（不在不知道绑定关系时归档）。 |
| `local_skills.py` | `scan_local_skills` → `LocalSkillScan(skills, installed_names)`：sweep、合并（预览/执行）、健康探针、技能医生（`get_skill_diagnostics`）共用的唯一技能扫描入口，每次调用各自重新扫描。`installed_names` = 带市场 `origin.json` 的技能 ∪ 位于非主目录（`DEFAULT_LOCAL_SKILL_PATHS` 第 0 项以外，即 Cursor/Claude/Codex 等其他工具的目录）的技能；仅当 `protect_installed_skills` 开启时由引擎当作豁免名单（与 `protected_names` 同构，按名称匹配）。 |
| `consolidation.py` | 技能合并（umbrella merge）集成：`run_consolidation_preview`/`run_consolidation_execute`，与 sweep 共享锁。被智能体、未完成 cron 任务或仍可运行看板任务绑定的技能作 `protected_names` 不参与合并，因此不存在需要改写的引用（响应只含归档/创建/净减少计数与摘要）。 |
| `consolidation_plan_token.py` | 合并「预览 → 执行」之间的短时凭据：`issue_plan_token` 对计划内容（`json.dumps(sort_keys=True)` 后 SHA-256）签发 900 秒有效的随机令牌，`validate_plan_token` 要求令牌未过期且指纹与当前计划一致，`revoke_plan_token` 在放行后立即注销，使「预览看到的计划」与「真正执行的计划」必须是同一个，并让凭据一次性。API 在 execute 前重新预览、比对指纹后才调用合并（`app/api/skills/curator.py`）。 |

---

## 依赖关系

**被依赖**：
- `app/api/skills/` — 技能 API
