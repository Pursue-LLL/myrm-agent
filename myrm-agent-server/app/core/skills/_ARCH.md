# core/skills 模块架构


---

## 架构概述

技能存储与管理，连接业务层和框架层。提供技能模型、CRUD 服务、打包/解包、本地提供者及 SkillBackend 工厂。专注于「适配」而非「实现」。通用能力（打包、历史记录与统计）由 PyPI `myrm-agent-harness` 提供，Server 层仅保留适配包装代码。

详细设计请参考 [SKILLS_SYSTEM.md](SKILLS_SYSTEM.md)

**Catalog vs Runtime（OAuth 集成技能）**：`oauth_availability.py` 在 Skills HTTP API 与 `loader.create_skill_backend()` 外包 `IntegrationOAuthSkillBackend`，使 `google-workspace` 等在 OAuth 未连接时 Catalog 与 Agent preload WARNING 一致。`enabled_prebuilt_ids` 白名单过滤由 `loader.create_skill_backend()` 统一承载，GeneralAgent 与 CustomAgent 均按用户启用清单注入该白名单，保持 Catalog 与 Runtime 的 prebuilt 可见性契约一致。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|-----|------|------|-------|
| `__init__.py` | 核心 | 模块入口，公共 API 导出 | — |
| `models.py` | 核心 | Skill、UserSkillConfig、SkillType 等数据模型 | — |
| `loader.py` | 核心 | 技能后端工厂，组装 SkillBackend。支持 `allowed_prebuilt_ids` 白名单过滤 prebuilt 技能（Action Space Opt-In）。 | ✅ |
| `prebuilt_sync.py` | 核心 | 预置技能种子同步（SKILL.md 三方哈希保护用户修改、upstream 更新检测；`scripts/` 等 bundle 文件始终跟随上游）与幽灵清理 | ✅ |
| `oauth_availability.py` | 核心 | Integration 凭证 gate：OAuth / xAI provider / skill env / CLI bins → `available` / `unavailable_reason`（Catalog + loader wrapper）。x-live-search 仅 gate xAI，不要求 Agent Web Search | ✅ |
| `x_live_search_skill_enable.py` | 核心 | xAI provider 保存后 auto-enable `x-live-search` prebuilt skill（respect disabled_prebuilt_ids） | ✅ |
| `assets/prebuilt_skills/` | 内容 | 官方 SKILL.md 种子库（见仓库根 `assets/prebuilt_skills/`）。边界见 [SKILLS_SYSTEM.md §3.5](SKILLS_SYSTEM.md) | ✅ |
| `state_reader.py` | 核心 | SkillStateReader 实现（SQLite 隔离状态查询） | ✅ |
| `storage_adapters.py` | 核心 | SnapshotStore/ABTestStore 协议适配器 | ✅ |
| `utils.py` | 核心 | 技能名称标准化（normalize_skill_name） | — |
| `store/service.py` | 核心 | 技能 CRUD 服务 | — |
| `store/reader.py` | 核心 | 技能读取 | — |
| `store/sanitizer.py` | 核心 | 技能内容清洗 | — |
| `store/user_config.py` | 核心 | 用户技能配置（enabled/disabled prebuilt、本地路径） | ✅ |
| `packaging/__init__.py` | 核心 | 技能打包业务 Facade 适配 | — |
| `history_tracking_service.py` | 核心 | 技能用量历史统计的业务 Facade 适配 | — |
| `providers/local.py` | 核心 | 本地文件系统技能提供者 | — |
| `config_version.py` | 核心 | 技能配置版本号管理（bump/get，Agent 热重载检测） | ✅ |
| `state_manager_instance.py` | 核心 | 全局 SkillStateManager 单例（init/get） | ✅ |
| `curator_service.py` | 核心 | Skill Curator 业务服务 — 配置持久化、sweep 执行、background task 编排、审计历史、consolidation 集成；`get_stats_collector()` 注入 harness `usage_recorder` | ✅ |
| `disabled_skill_roots.py` | 核心 | 收集用户未启用技能的 `storage_path` 根目录，注入 agent runtime context 供 glob/grep/file_read 过滤 | ✅ |

---

## 依赖关系

**内部依赖**：
- `app/core/toolkits/storage/` — 对象存储抽象（如使用）

**外部依赖**：
- `myrm_agent_harness` — 底层通用 Agent 引擎及其技能生命周期能力（打包解包、用量历史统计）

**被依赖**：
- `app/api/skills/` — 技能 API
- `app/ai_agents/` — Agent 技能工具