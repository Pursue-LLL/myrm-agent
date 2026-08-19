# skills/packaging 模块架构


---

## 架构概述

Server 层技能打包 Facade：调用 PyPI `myrm-agent-harness` 的 `SkillPacker` / `SkillUnpacker` 与校验 API，对接业务 Workspace；导出前经 `content_sanitizer` 脱敏，支持两段式 Diff 预览与细粒度密钥剥离。

导出时从 evolution SkillStore 读取 `SkillRecord.eval_cases` 序列化为包内 `evals.json`（自动脱敏），并同步 `SKILL.md` frontmatter `version` 为 lineage 真实版本；导入时剥离 `evals.json` 校验并还原到 evolution SkillStore（仅第一个有效者胜出；还原前刷新 `updated_at`），保证回归门禁跨实例迁移不丢失。`evals.json` 为包内保留名：导出侧跳过技能目录中同名手写文件，仅由快照逻辑生成；导入侧剥离所有层级的 `evals.json`，不写入技能存储目录。

---

## 文件清单

| 文件 | 地位 | 职责| I/O/P |
|------|------|------|-------|
| `__init__.py` | ✅ 核心 | `SkillPackagingService` 服务暴露，包装 Harness 打包能力（支持 Agent Plugins 1.0.0 与 Raw Skill 格式导出），集成脱敏引擎与 eval_cases/version 同步 | — |
| `_helpers.py` | 辅助 | `_load_evolution_record` / `_sync_skill_md_version` 内部辅助函数 | — |
| `_models.py` | 类型 | `PackageResult` / `UnpackResult` 打包/解包结果数据类 | — |