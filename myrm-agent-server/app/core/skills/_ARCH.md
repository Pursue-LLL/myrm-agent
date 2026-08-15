# core/skills 模块架构


---

## 架构概述

技能存储与管理，连接业务层和框架层。提供技能模型、CRUD 服务、打包/解包、本地提供者及 SkillBackend 工厂。专注于「适配」而非「实现」。通用能力（打包、历史记录与统计）由 PyPI `myrm-agent-harness` 提供，Server 层仅保留适配包装代码。

详细设计请参考 [SKILLS_SYSTEM.md](SKILLS_SYSTEM.md)

**Catalog vs Runtime（OAuth 集成技能）**：`gates/oauth_availability.py` 在 Skills HTTP API 与 `loader.create_skill_backend()` 外包 `IntegrationOAuthSkillBackend`，使 `google-workspace` 等在 OAuth 未连接时 Catalog 与 Agent preload WARNING 一致。`enabled_prebuilt_ids` 白名单过滤由 `loader.create_skill_backend()` 统一承载，GeneralAgent 与 CustomAgent 均按用户启用清单注入该白名单，保持 Catalog 与 Runtime 的 prebuilt 可见性契约一致。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|-----|------|------|-------|
| `__init__.py` | 核心 | 模块入口，公共 API 导出 | — |
| `models.py` | 核心 | Skill、UserSkillConfig、SkillType 等数据模型 | — |
| `loader.py` | 核心 | 技能后端工厂，组装 SkillBackend。支持 `allowed_prebuilt_ids` 白名单过滤 prebuilt 技能（Action Space Opt-In）。 | ✅ |
| `prebuilt_sync.py` | 核心 | 预置技能种子同步（SKILL.md 三方哈希保护用户修改、upstream 更新检测；`scripts/` 等 bundle 文件始终跟随上游）与幽灵清理 | ✅ |
| `assets/prebuilt_skills/` | 内容 | 官方 SKILL.md 种子库（见仓库根 `assets/prebuilt_skills/`）。边界见 [SKILLS_SYSTEM.md §3.5](SKILLS_SYSTEM.md) | ✅ |
| `state_reader.py` | 核心 | SkillStateReader 实现（SQLite 隔离状态查询，默认复用进化存储单例） | ✅ |
| `storage_adapters.py` | 核心 | SnapshotStore/ABTestStore 协议适配器 | ✅ |
| `utils.py` | 核心 | 技能名称标准化（normalize_skill_name） | — |
| `store/__init__.py` | 子域 | 存储层聚合出口：CRUD 服务 + 用户配置 + 转发 harness sanitizer（`myrm_agent_harness.agent.skills.market.sanitizer`） | — |
| `store/service.py` | 核心 | 技能 CRUD 服务 | — |
| `store/reader.py` | 核心 | 技能读取 | — |
| `store/evolution_store.py` | 核心 | 进化技能存储进程级单例（get/reset，热读路径复用） | ✅ |
| `store/user_config.py` | 核心 | 用户技能配置（enabled/disabled prebuilt、本地路径） | ✅ |
| `packaging/__init__.py` | 核心 | 技能打包业务 Facade 适配（转发 harness packer/validator） | — |
| `packaging/_helpers.py` | 内部 | 打包内部辅助（`_load_evolution_record`/`_sync_skill_md_version`） | — |
| `packaging/_models.py` | 内部 | 打包内部模型（Redaction 脱敏条目转发） | — |
| `providers/local.py` | 核心 | 本地文件系统技能提供者 | — |
| `creation/__init__.py` | 子域 | 技能创作域聚合出口 | — |
| `creation/service.py` | 核心 | SkillCreationService（SkillWriteBackend 本地文件系统实现 + 单例） | ✅ |
| `config_version.py` | 核心 | 技能配置版本号管理（bump/get，Agent 热重载检测） | ✅ |
| `state_manager_instance.py` | 核心 | 全局 SkillStateManager 单例（init/get） | ✅ |
| `curator/__init__.py` | 子域 | 技能生命周期治理域聚合出口 | — |
| `curator/service.py` | 核心 | Curator 业务服务 — sweep/配置/历史/后台任务编排；`get_stats_collector()` 注入 harness `usage_recorder` | ✅ |
| `curator/consolidation.py` | 核心 | 技能合并（umbrella merge）集成 — preview/execute/agent refs 重写，共享 sweep 锁 | ✅ |
| `effective_skill_ids.py` | 核心 | Agent 空 allowlist 时解析运行时 skill_ids（enabled prebuilt + local） | ✅ |
| `discovery/` | 子域 | 技能发现聚合出口：`adopt`（显式 allowlist 时 install 自动 append）、`mount`（安装/更新后 catalog enable）、`autoupdate`（上游版本检测） | ✅ |
| `marketplace/` | 子域 | 市场聚合出口：`market_service`（GitHub 源分析、自定义源、ClawHub 镜像懒加载）、`clawhub_registry`（镜像 URL 持久化/apply，CLAWHUB_URL SSOT）、`clawhub_probe`（连通性探测）、`custom_source_config`（自定义源持久化） | ✅ |
| `gates/` | 子域 | 集成 gate 聚合出口：`oauth_availability`（OAuth/xAI/env/CLI bins 凭证 gate）、`x_live_search_skill_enable`（xAI provider 保存后 auto-enable）、`disabled_skill_roots`（未启用技能 storage 根注入 runtime）、`dependency_guard`（依赖影响面查询）、`permission_logger`（权限使用日志） | ✅ |

---

## 依赖关系

**内部依赖**：
- `app/core/toolkits/storage/` — 对象存储抽象（如使用）

**外部依赖**：
- `myrm_agent_harness` — 底层通用 Agent 引擎及其技能生命周期能力（打包解包、用量历史统计）

**被依赖**：
- `app/api/skills/` — 技能 API
- `app/ai_agents/` — Agent 技能工具