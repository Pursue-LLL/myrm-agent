# app/services/skill_optimization 模块架构


---

## 架构概述

Agent 技能自动优化服务。包含观测（A/B 测试 + 影子执行）、决策（LLM 分析 + 语义合并）、分发（基线同步 + 回滚）三阶段。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ab_test_manager.py` | 中枢控制器 | 托管队列 + 统一数据流 + 采样率决策 + Auto-Promote | ✅ |
| `shadow_tester.py` | 验证引擎 | 隔离沙箱中静默执行候选版本并比对结果 | ✅ |
| `semantic_comparator.py` | 语义判官 | 继承 Harness 层 StructuredComparator，按需调用 LLM 语义判定 | ✅ |
| `execution_provider.py` | 执行适配器 | 桥接 Harness 层的执行能力 | ✅ |
| `llm_optimizer.py` | 进化大脑 | 调用 LLM 根据性能反馈重新生成提示词 | ✅ |
| `baseline_syncer.py` | 状态同步 | 确保内存与数据库中的 Master 版本一致 | ✅ |
| `rollback_service.py` | 安全回滚 | Batch 快照创建与回滚编排（`create_batch_snapshot` / `rollback_batch`） | ✅ |
| `skill_version_sync.py` | 双写同步 | DB 快照与磁盘 SKILL.md 原子同步；`start_shadow_ab_test` 供进化 shadow 与 API 共用（返回复合 `test_id`） | ✅ |
| `semantic_merger.py` | 冲突合并 | 多版本优化时的语义合并工具 | ✅ |
| `notification_service.py` | 通知中心 | 发送优化成功、A/B 测试分歧等告警 | ✅ |
| `scheduler.py` | 调度器 | 优化任务调度 | ✅ |
| `scheduler_factory.py` | 工厂 | 调度器创建工厂 | ✅ |
| `bootstrap.py` | 核心 | 技能优化服务单例注册（scheduler/storage/emitter/aggregator） | ✅ |
| `metrics_provider.py` | 核心 | Evolution 漏斗指标提供者（`EvolutionMetricsProvider`） | ✅ |
| `reporter.py` | 报告 | 优化报告生成 | ✅ |
| `telemetry_pusher.py` | 遥测 | 遥测数据推送 | ✅ |
| `time_estimator.py` | 估算器 | 优化时间估算 | ✅ |
| `federated_extractor.py` | 提取器 | 联邦学习数据提取 | ✅ |

---

## 依赖关系

- `app/adapters/skill_optimization/`：数据访问层
- `app/database/models/skill_optimization/`：ORM 模型（SkillVersion、BatchSnapshot 等）
- `myrm_agent_harness`：Agent 执行能力、StructuredComparator 等

## 测试

`tests/services/skill_optimization/test_skill_version_integration.py` 覆盖 `restore_skill_snapshot` 双分支真写盘；`tests/api/batch_optimization/test_cancel_rollback.py` 覆盖 `rollback_batch` 全量/部分失败；HTTP cancel 真链见 `test_cancel_rollback_http_integration.py`。`tests/conftest.py` 自动注入 monorepo harness `PYTHONPATH`（见 `app/api/batch_optimization/_ARCH.md`）。
