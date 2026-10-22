# skills/store 模块架构


---

## 架构概述

Skill 商店模块。管理 Skill 的 CRUD、用户配置、读取和安全清洗。

---

## 文件清单

| 文件 | 地位 | 职责| I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域 | 存储层聚合出口：导出 SkillsService / UserSkillConfigManager，并转发 harness 的 `market.sanitizer`（`SKILL_MD_FILE`、`SKILL_NAME_PATTERN`、`sanitize_skill_files`） |
| `service.py` | ✅ 核心 | Skill 商店服务（CRUD、搜索、安装）；`get_skills_by_ids` / `get_user_available_skills` 经 `gates.runtime_load` 排除归档与禁用技能 |
| `evolution_store.py` | ✅ 辅助 | 进化 SkillStore SQLite 访问（core/services 共用）——进程级单例缓存（`get_evolution_skill_store`），只读调用点不再 close 共享实例；`reset_evolution_skill_store` 供测试隔离 |
| `reader.py` | ✅ 核心 | Skill 读取器（解析 Skill 包内容）；整盘本地技能扫描会逐个解析 SKILL.md 并跑安全模式（24 个技能约 1 秒，结果不缓存、每次调用重扫），故 `list_local_skills` 与 `SkillsService.get_skill` 经 `scan_off_loop` 交给单线程 worker，事件循环不被冻结；单 worker 因扫描受 GIL 限制，重叠只会互相拖慢 |
| `user_config.py` | ✅ 辅助 | 用户 Skill 配置（个人偏好、启用/禁用） |
