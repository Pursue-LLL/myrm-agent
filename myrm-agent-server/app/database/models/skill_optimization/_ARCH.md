# database/models/skill_optimization/

## 架构概述

技能版本历史、批次撤销快照与技能包修订 ORM 模型。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Skill Optimization Models | ✅ |
| `batch_snapshot.py` | 模块 | Batch Snapshot Model（技能修改批次撤销快照） | ✅ |
| `skill_version.py` | 模块 | 定义skill_versions表的ORM模型，用于记录skill的每个版本，支持版本回滚。 | ✅ |
| `skill_package_revision.py` | 模块 | 技能包修订快照（SKILL.md + 资源文件 blob） | ✅ |
