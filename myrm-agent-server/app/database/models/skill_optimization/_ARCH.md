# database/models/skill_optimization/

## 架构概述

技能优化 ORM 模型。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Skill Optimization Models | ✅ |
| `ab_test_result.py` | 模块 | A/B Test Result Model | ✅ |
| `batch_snapshot.py` | 模块 | Batch Snapshot Model（技能修改批次撤销快照） | ✅ |
| `optimization_record.py` | 模块 | Optimization Record Model | ✅ |
| `shadow_sample.py` | 模块 | Shadow Test Sample Model | ✅ |
| `skill_quality_history.py` | 模块 | Skill Quality History Model | ✅ |
| `skill_version.py` | 模块 | 定义skill_versions表的ORM模型，用于记录skill的每个版本，支持版本回滚。 | ✅ |
| `skill_package_revision.py` | 模块 | 技能包修订快照（SKILL.md + 资源文件 blob） | ✅ |
