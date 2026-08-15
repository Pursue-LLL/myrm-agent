# services/memory/archive 模块架构

## 架构概述

单用户 Memory Archive 导出与审查预检、单用户 Memory Archive 安全合并恢复与回滚账本。提供归档分区 dry-run、payload/plan hash 强校验、恢复前安全预检、journaled safe-merge 恢复、关系型恢复账本、恢复后诊断 metadata 挂载、中断恢复回滚、profile 并发保护、Shared Context/会话/回放/审计恢复和精准回滚，不包含多租户或控制平面语义。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `archive.py` | 核心 | 单用户 Memory Archive 服务。基于 Harness archive DTO 聚合普通记忆、Shared Context、会话、回放事件和记忆审计账本，执行内容脱敏并提供导入前结构校验，不包含多租户或控制平面语义。replay 分区**恒为空**（agent 事件回放以 harness JSONL event-log 为准） | ✅ |
| `restore/`（子包） | 核心 | 归档恢复子域：`archive_restore.py`（MemoryArchiveRestoreService 门面）、`archive_restore_common.py`（共享原语）、`archive_restore_executor.py`、`archive_restore_planner.py`、`archive_restore_rollback.py`。`restore/__init__.py` 为聚合门面 | ✅ |
