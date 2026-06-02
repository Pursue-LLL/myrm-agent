# skills/providers 模块架构


---

## 架构概述

Skill 提供者模块。实现不同来源的 Skill 加载和管理。

---

## 文件清单

| 文件 | 地位 | 职责| I/O/P |
|------|------|------|-------|
| `local.py` | ✅ 核心 | 本地 Skill 提供者（文件系统加载、热更新、.stats.json lifecycle 注入） |
