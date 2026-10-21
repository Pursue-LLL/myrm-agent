# app/services/skill_optimization 模块架构


---

## 架构概述

技能版本服务：版本以 DB 快照与磁盘 SKILL.md 双写同步，支持一键回滚；技能修改批次的前快照在此落库。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `rollback_service.py` | 快照写入 | `insert_mutation_batch_snapshot` 写入 `batch_snapshots`（恢复由 `services/skills/mutation_batch_service.py` 执行）；每行带显式、进程内严格递增的 `created_at`：撤销时据此判断同一 skill 是否还有更晚的批次，库默认的 `CURRENT_TIMESTAMP` 只有秒级精度，同一秒内的两个批次会分不出先后 | ✅ |
| `skill_version_sync.py` | 双写同步 | DB 快照与磁盘 SKILL.md 原子同步：`persist_skill_version`、`activate_version_with_disk_sync`、`restore_skill_snapshot`、`sync_content_to_disk` | ✅ |
| `bootstrap.py` | 核心 | `get_skill_optimization_storage()`：绑定当前 session factory 的 `SQLAlchemyStorage`（API/services 共用） | ✅ |

---

## 依赖关系

- `app/adapters/skill_optimization/`：数据访问层
- `app/database/models/skill_optimization/`：ORM 模型（SkillVersion、BatchSnapshot 等）
- `myrm_agent_harness`：`SkillVersion` 与 `SkillOptimizationStorage` 协议

## 测试

`tests/services/skill_optimization/test_skill_version_integration.py` 覆盖 `restore_skill_snapshot` 双分支真写盘；`test_rollback_service.py` 覆盖快照写入与 `get_skill_optimization_storage()` 绑定真实 SQLAlchemy 存储；批次撤销 HTTP 链见 `tests/api/skill_optimization/test_mutation_batch_rollback_http.py`。`tests/conftest.py` 自动注入 monorepo harness `PYTHONPATH`。
