# services/memory/durable_revision 模块架构

## 架构概述

持久化修订与并发写入：维护 Harness `DurableRevisionSuite` 单例，并在 Harness 领域对象（`WritePayload` / `ChangeReceipt` / `SnapshotReadView`）与 `app.schemas.durable_revision` DTO 之间做转换，提供写入、快照读取、回执查询、回滚、撤回与统计。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 辅助 | 包标识 | ✅ |
| `provider.py` | 核心 | `get_durable_revision_suite` / `reset_durable_revision_suite` 单例；`execute_durable_write` / `query_snapshot` / `query_receipt` / `execute_rollback` / `execute_retract` / `get_revision_stats` 业务入口；`_to_receipt_dto` / `_to_snapshot_dto` 转换 | ✅ |
