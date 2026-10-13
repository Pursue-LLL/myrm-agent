# app/services/skill_optimization 模块架构


---

## 架构概述

技能版本与影子 A/B 服务：候选版本在隔离沙箱中影子执行并比对结果，经上线门控后晋升；版本以 DB 快照与磁盘 SKILL.md 双写同步；技能修改批次的前快照在此落库。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ab_test_manager.py` | 中枢控制器 | 托管队列 + 统一数据流 + 采样率决策 + Auto-Promote | ✅ |
| `shadow_tester.py` | 验证引擎 | 隔离沙箱中静默执行候选版本并比对结果 | ✅ |
| `semantic_comparator.py` | 语义判官 | 继承 Harness 层 StructuredComparator，按需调用 LLM 语义判定 | ✅ |
| `execution_provider.py` | 执行适配器 | 实现 Harness 的 `SkillExecutionProvider`：`execute_skill_version` 供影子测试；执行样本经 `EventLogAdapter` 读取 JSONL event_log；元数据经 `SkillsService` | ✅ |
| `rollback_service.py` | 快照写入 | `insert_mutation_batch_snapshot` 写入 `batch_snapshots`（恢复由 `services/skills/mutation_batch_service.py` 执行） | ✅ |
| `skill_version_sync.py` | 双写同步 | DB 快照与磁盘 SKILL.md 原子同步；`start_shadow_ab_test` 供进化 shadow 与 API 共用（返回复合 `test_id`） | ✅ |
| `bootstrap.py` | 核心 | `get_skill_optimization_storage()`：绑定当前 session factory 的 `SQLAlchemyStorage`（API/services 共用） | ✅ |
| `runtime.py` | 核心 | 进程级 `ABTestManager` 启动/关闭；HTTP `get_ab_test_manager` 与 lifecycle 共用 | ✅ |

---

## 依赖关系

- `app/adapters/skill_optimization/`：数据访问层
- `app/database/models/skill_optimization/`：ORM 模型（SkillVersion、BatchSnapshot 等）
- `myrm_agent_harness`：Agent 执行能力、StructuredComparator 等

## 测试

`tests/services/skill_optimization/test_skill_version_integration.py` 覆盖 `restore_skill_snapshot` 双分支真写盘；`test_rollback_service.py` 覆盖快照写入与 `get_skill_optimization_storage()` 绑定真实 SQLAlchemy 存储；批次撤销 HTTP 链见 `tests/api/skill_optimization/test_mutation_batch_rollback_http.py`。`tests/conftest.py` 自动注入 monorepo harness `PYTHONPATH`。
