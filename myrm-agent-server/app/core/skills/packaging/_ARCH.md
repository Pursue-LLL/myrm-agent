# skills/packaging 模块架构


---

## 架构概述

（v2026-04-21 架构演进说明：原打包核心逻辑已完全下沉至 `myrm-agent-harness` 引擎层）
当前模块仅作为业务层（Server）的极薄 Facade（外观模式）适配器，直接调用 Harness 提供的 `SkillPacker`, `SkillUnpacker` 和校验方法。
负责对接业务层的 Workspace 概念。

---

## 文件清单

| 文件 | 地位 | 职责| I/O/P |
|------|------|------|-------|
| `__init__.py` | ✅ 核心 | `SkillPackagingService` 服务暴露，包装 Harness 打包能力 | 待补 |