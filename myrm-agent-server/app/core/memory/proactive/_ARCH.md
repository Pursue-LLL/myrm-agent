# core/commitment/

## 架构概述

Commitment 承诺段提取与 SQLite 存储。Harness 抽取引擎：`myrm_agent_harness.toolkits.memory.proactive`（见 harness 包内 `COMMITMENT_SYSTEM.md`）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Commitment tracking — server-layer implementation. | ✅ |
| `extraction_hook.py` | 模块 | Server-layer integration point. | ✅ |
| `section.py` | 模块 | Heartbeat integration for the commitment system. | ✅ |
| `sqlite_store.py` | 模块 | Server-layer SQLite commitment store. | ✅ |
