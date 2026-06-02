# app/adapters/skill_optimization 模块架构


---

## 架构概述

技能优化系统的数据访问层（Data Access Layer），采用 Repository Pattern 封装数据库操作。
通过 SQLAlchemyStorage 适配器实现 harness 框架的 `SkillOptimizationStorage` Protocol。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `optimization_repo.py` | 核心 | 优化记录 CRUD | ✅ |
| `quality_repo.py` | 核心 | 质量历史 CRUD | ✅ |
| `ab_test_repo.py` | 核心 | A/B 测试 CRUD | ✅ |
| `batch_task_repo.py` | 核心 | 批量任务 CRUD | ✅ |
| `snapshot_repo.py` | 核心 | 快照管理 CRUD | ✅ |
| `audit_log_repo.py` | 核心 | 审计日志 CRUD | ✅ |
| `heavy_analytics_repo.py` | 核心 | 重度分析（OLAP） | ✅ |
| `sqlalchemy_storage.py` | 核心 | 框架适配器，实现 `SkillOptimizationStorage` Protocol | ✅ |

---

## 依赖关系

- `app/database/models.py`：SQLAlchemy ORM 模型
- `myrm_agent_harness`：`SkillOptimizationStorage` Protocol 定义
