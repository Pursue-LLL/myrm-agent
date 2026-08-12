# app/core/skills/gates 子包架构


---

## 架构概述

集成技能可用性、权限、隔离与依赖 gate 子域。保证 Catalog 与 Runtime 对集成技能（OAuth 凭证、环境变量、CLI bins）的可见性契约一致，并承载未启用技能隔离、依赖影响面查询与权限使用日志。属于 Server 业务层。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 子域聚合出口：导出各 gate 公共 API。 |
| `oauth_availability.py` | Integration 凭证 gate：`IntegrationOAuthSkillBackend` 包装，`apply_integration_oauth_availability`/`enrich_skill_metadata_integration_oauth` 使 Google Workspace / Notion / Linear / xAI 等在 OAuth 未连接时 Catalog 与 Agent preload 一致降级。 |
| `x_live_search_skill_enable.py` | xAI provider 保存后 auto-enable prebuilt skill：`maybe_enable_x_live_search_skill`。 |
| `disabled_skill_roots.py` | 未启用技能 storage 根注入 runtime：`collect_disabled_skill_roots`。 |
| `dependency_guard.py` | 技能依赖影响面查询：`get_dependents_map`/`get_dependents_for_skill`（pending 审核 / disable / uninstall 校验）。 |
| `permission_logger.py` | 技能权限使用日志：`start_permission_logger`。 |

---

## 依赖关系

**被依赖**：
- `app/core/skills/loader.py` — SkillBackend 工厂包装
- `app/api/skills/` — 技能 API
