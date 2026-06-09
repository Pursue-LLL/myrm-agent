# skills/packaging 模块架构


---

## 架构概述

Server 层技能打包 Facade：调用 PyPI `myrm-agent-harness` 的 `SkillPacker` / `SkillUnpacker` 与校验 API，对接业务 Workspace；导出前经 `content_sanitizer` 脱敏，支持两段式 Diff 预览与细粒度密钥剥离。

---

## 文件清单

| 文件 | 地位 | 职责| I/O/P |
|------|------|------|-------|
| `__init__.py` | ✅ 核心 | `SkillPackagingService` 服务暴露，包装 Harness 打包能力，集成脱敏引擎 | — |