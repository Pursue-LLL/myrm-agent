# skills/providers 模块架构


---

## 架构概述

Skill 提供者模块。实现不同来源的 Skill 加载和管理。

---

## 文件清单

| 文件 | 地位 | 职责| I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 模块门面：统一导出 `LocalSkillsProvider` 与 `preview_skill_path` | ✅ |
| `local.py` | ✅ 核心 | 本地 Skill 提供者（文件系统单/多目录自适应加载、热更新、.stats.json lifecycle 注入） |
| `local_preview.py` | ✅ 核心 | 本地 Skill 路径 dry-run 探测、安全路径穿越防御 (CWE-22)、全量静态代码穿透安全扫描与评分诊断工具库 |
