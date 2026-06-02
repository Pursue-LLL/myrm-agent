# models/skill_optimization 模块架构


## 架构概述

技能优化相关 SQLAlchemy ORM 模型。定义 A/B 测试、优化记录、质量历史等数据库表。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 模型导出 | — |
| `optimization_record.py` | 核心 | 优化记录模型 | ⚠️ 待补 |
| `skill_quality_history.py` | 核心 | 质量历史模型 | ⚠️ 待补 |
| `ab_test_result.py` | 核心 | A/B 测试结果模型 | ⚠️ 待补 |
| `shadow_sample.py` | 核心 | 影子测试样本模型 | ⚠️ 待补 |
| `skill_version.py` | 核心 | 技能版本模型 | ⚠️ 待补 |
| `batch_task.py` | 核心 | 批量优化任务模型 | ⚠️ 待补 |
| `batch_audit_log.py` | 辅助 | 批量优化审计日志模型 | ⚠️ 待补 |
| `batch_snapshot.py` | 辅助 | 批量快照模型 | ⚠️ 待补 |
