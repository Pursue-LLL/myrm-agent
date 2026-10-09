# services/memory/experience_compounding 模块架构

## 架构概述

经验复利与知识凝练：`ExperienceCompoundingServiceProvider` 持有 Harness `ExperienceCompoundingSuite` 单例（`get_experience_compounding_service`），对外提供经验新增、强化、惩罚、凝练为 Golden Rule、反凝练、租约退火、活跃项/规则列表与统计，DTO 来自 `app.schemas.experience_compounding`；首次实例化时写入种子经验（`_bootstrap_seeded_experiences`）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 辅助 | 导出 provider 公共入口 | ✅ |
| `provider.py` | 核心 | `ExperienceCompoundingServiceProvider`：add_experience / reinforce / penalize / condense / decondense / anneal / list_active / list_rules / get_stats；`get_experience_compounding_service` 单例入口 | ✅ |
