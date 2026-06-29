# core/memory/proactive/

## 架构概述

Proactive follow-up（智能跟进）领域实现。Harness 抽取引擎：`myrm_agent_harness.toolkits.memory.proactive`（见 `COMMITMENT_SYSTEM.md`）。HTTP 在 `api/memory/follow_ups/`（`/memory/follow-ups`）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Proactive follow-up — server-layer implementation. | ✅ |
| `settings.py` | 模块 | `resolve_memory_enabled` — 与 schema 默认 False 一致。 | ✅ |
| `delivery_tracker.py` | 模块 | ContextVar 追踪 heartbeat 注入项；非 `[SILENT]` 响应标记 SENT，否则自动 snooze 6h。确认入口：`agent_runner._finalize_heartbeat_follow_up_delivery()` | ✅ |
| `extraction_hook.py` | 模块 | 会话结束抽取 hook，持久化到 SQLite。 | ✅ |
| `section.py` | 模块 | Heartbeat situation 段注入；`memory_enabled=False` 时跳过。 | ✅ |
| `sqlite_store.py` | 模块 | Server-layer SQLite `CommitmentStore` 实现。 | ✅ |
