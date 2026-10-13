# api/skill_optimization/

## 架构概述

技能版本与影子 A/B HTTP 层：版本列表/对比/回滚、技能修改批次撤销（`/mutations/{id}/rollback`）、技能包修订、Shadow A/B 测试。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Skill Optimization API | ✅ |
| `dependencies.py` | 模块 | FastAPI 依赖：`get_storage`、`get_event_emitter`、`get_ab_test_manager` | ✅ |
| `router.py` | 路由 | Skill Optimization API Router | ✅ |
