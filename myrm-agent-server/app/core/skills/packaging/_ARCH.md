# skills/packaging 模块架构


---

## 架构概述

Server 层技能打包 Facade：调用 PyPI `myrm-agent-harness` 的 `SkillPacker` / `SkillUnpacker` 与校验 API，对接业务 Workspace；导出前经 `content_sanitizer` 脱敏（`redaction.py` 为单技能导出、专家导出、Marketplace 导出共用的唯一脱敏通道），支持两段式 Diff 预览与细粒度密钥剥离；预览返回文件树摘要 `review_digest`，导出携带“忽略脱敏”决定（`ignored_redactions` 非空）时必须与当前文件树一致，否则以 `skill_changed_since_preview` 拒绝（防止技能在预览后被改动导致忽略索引指向另一处密钥；仅 `apply_redactions` 是单向收紧，无需摘要）。

导出时从 evolution SkillStore 读取 `SkillRecord.eval_cases` 序列化为包内 `evals.json`（自动脱敏），并同步 `SKILL.md` frontmatter `version` 为 lineage 真实版本；导入时剥离 `evals.json` 校验并还原到 evolution SkillStore（仅第一个有效者胜出；还原前刷新 `updated_at`），保证回归门禁跨实例迁移不丢失。`evals.json` 为包内保留名：导出侧跳过技能目录中同名手写文件，仅由快照逻辑生成；导入侧剥离所有层级的 `evals.json`，不写入技能存储目录。

---

## 文件清单

| 文件 | 地位 | 职责| I/O/P |
|------|------|------|-------|
| `__init__.py` | ✅ 核心 | `SkillPackagingService` 服务暴露，包装 Harness 打包能力（支持 Agent Plugins 1.0.0 与 Raw Skill 格式导出），集成脱敏引擎与 eval_cases/version 同步 | — |
| `_helpers.py` | 辅助 | `_load_evolution_record` / `_sync_skill_md_version` 内部辅助函数 | — |
| `collect.py` | 核心 | `collect_skill_files` — 技能可导出文件树采集（排除安装簿记 `origin.json`/`receipt.json`/存储元数据/`evals.json`，同步 SKILL.md 版本） | — |
| `redaction.py` | 核心 | `redact_files` / `review_digest` — 纯函数脱敏通道（二进制不解码、不改写；扫描在线程池执行）与预览文件树摘要 | — |
| `_models.py` | 类型 | `PackageResult`（含 `review_digest` / `error_code`）/ `UnpackResult` 打包/解包结果数据类，`SKILL_CHANGED_SINCE_PREVIEW` 错误码 | — |