# app/adapters/skill_optimization 模块架构


---

## 架构概述

技能版本历史的数据访问层（Data Access Layer），采用 Repository Pattern 封装数据库操作。
通过 SQLAlchemyStorage 适配器实现 harness 框架的 `SkillOptimizationStorage` Protocol。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `snapshot_repo.py` | 核心 | skill_versions 表 CRUD（由 `skill_version_sync` 双写接入） | ✅ |
| `sqlalchemy_storage.py` | 核心 | 框架适配器，实现 `SkillOptimizationStorage` Protocol；每次操作使用独立 session | ✅ |

---

## 依赖关系

- `app/database/models.py`：SQLAlchemy ORM 模型
- `myrm_agent_harness`：`SkillOptimizationStorage` Protocol 定义
