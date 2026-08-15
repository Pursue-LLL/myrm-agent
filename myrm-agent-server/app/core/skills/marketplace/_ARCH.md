# app/core/skills/marketplace 子包架构


---

## 架构概述

技能市场、镜像注册表与自定义源子域。提供业务层市场服务（GitHub 源分析、ClawHub 镜像懒加载）、ClawHub registry URL 持久化/apply（`CLAWHUB_URL` SSOT）、连通性探测与自定义技能源（`.well-known/skills`）持久化管理。属于 Server 业务层。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 子域聚合出口：导出市场/镜像/自定义源公共 API。 |
| `market_service.py` | 技能市场业务服务：`SkillMarketService`/`market_service` 单例（GitHub 源分析、镜像懒加载、卸载后清理权限数据）。 |
| `clawhub_registry.py` | ClawHub 镜像 URL 持久化/apply：`get_registry_presets`/`normalize_clawhub_registry_url`/`apply_clawhub_registry_url`（`CLAWHUB_URL` SSOT）。 |
| `clawhub_probe.py` | ClawHub registry 连通性探测：`probe_clawhub_registry`/`probe_configured_cn_mirror`（薄封装 Harness）。 |
| `custom_source_config.py` | 自定义技能源持久化：`CustomSourceConfig`/`CustomSourceEntry`，`load/save/add/remove_custom_source`。 |

---

## 依赖关系

**被依赖**：
- `app/api/skills/` — 技能 API
