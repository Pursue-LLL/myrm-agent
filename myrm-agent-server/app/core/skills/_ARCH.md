# core/skills 模块架构


---

## 架构概述

技能存储与管理，连接业务层和框架层。提供技能模型、CRUD 服务、打包/解包、本地提供者及 SkillBackend 工厂。专注于「适配」而非「实现」。通用能力（打包、历史记录与统计）由 PyPI `myrm-agent-harness` 提供，Server 层仅保留适配包装代码。

详细设计请参考 [SKILLS_SYSTEM.md](SKILLS_SYSTEM.md)

**Catalog vs Runtime（已知差距）**：`enabled_prebuilt_ids` / Agent `skill_ids` 当前主要管 GUI 与 user skill 路由；`loader.create_skill_backend()` 仍将全量 prebuilt 暴露给 Agent `list_skills()`。目标：Catalog → Bound → Runtime 三层一致（实现细节见 [SKILLS_SYSTEM.md](SKILLS_SYSTEM.md)）。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|-----|------|------|-------|
| `__init__.py` | 核心 | 模块入口，公共 API 导出 | ⚠️ 待补 |
| `models.py` | 核心 | Skill、UserSkillConfig、SkillType 等数据模型 | ⚠️ 待补 |
| `loader.py` | 核心 | 技能后端工厂，组装 SkillBackend。支持 `allowed_prebuilt_ids` 白名单过滤 prebuilt 技能（Action Space Opt-In）。 | ✅ |
| `prebuilt_sync.py` | 核心 | 预置技能种子同步（三方哈希保护用户修改、upstream 更新检测）与幽灵清理 | ✅ |
| `assets/prebuilt_skills/` | 内容 | 官方 SKILL.md 种子库（见仓库根 `assets/prebuilt_skills/`） | ✅ |
| `state_reader.py` | 核心 | SkillStateReader 实现（SQLite 隔离状态查询） | ✅ |
| `storage_adapters.py` | 核心 | SnapshotStore/ABTestStore 协议适配器 | ✅ |
| `utils.py` | 核心 | 技能名称标准化（normalize_skill_name） | ⚠️ 待补 |
| `store/service.py` | 核心 | 技能 CRUD 服务 | ⚠️ 待补 |
| `store/reader.py` | 核心 | 技能读取 | ⚠️ 待补 |
| `store/sanitizer.py` | 核心 | 技能内容清洗 | ⚠️ 待补 |
| `store/user_config.py` | 核心 | 用户技能配置（enabled/disabled prebuilt、本地路径） | ✅ |
| `packaging/__init__.py` | 核心 | 技能打包业务 Facade 适配 | ⚠️ 待补 |
| `history_tracking_service.py` | 核心 | 技能用量历史统计的业务 Facade 适配 | ⚠️ 待补 |
| `providers/local.py` | 核心 | 本地文件系统技能提供者 | ⚠️ 待补 |
| `config_version.py` | 核心 | 技能配置版本号管理（bump/get，Agent 热重载检测） | ✅ |
| `state_manager_instance.py` | 核心 | 全局 SkillStateManager 单例（init/get） | ✅ |
| `curator_service.py` | 核心 | Skill Curator 业务服务 — 配置持久化、sweep 执行、background task 编排、审计历史、consolidation (Umbrella Merge) 集成与 agent 引用重写 | ✅ |

---

## 依赖关系

**内部依赖**：
- `app/core/toolkits/storage/` — 对象存储抽象（如使用）

**外部依赖**：
- `myrm_agent_harness` — 底层通用 Agent 引擎及其技能生命周期能力（打包解包、用量历史统计）

**被依赖**：
- `app/api/skills/` — 技能 API
- `app/ai_agents/` — Agent 技能工具