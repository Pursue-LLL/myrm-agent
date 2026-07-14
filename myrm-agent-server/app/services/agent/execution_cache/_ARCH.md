# execution_cache 模块

---

## 架构概述

Chat 级 `BuiltExecutionUnit` 池（SkillAgent + BrowserSession）。WebUI/Channel/Wakeup 走 POOLED；Cron/Eval/Kanban 走 EPHEMERAL。镜像 `ChatRuntimePoolRegistry` 生命周期语义。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `__init__.py` | 入口 | 公共导出 |
| `registry.py` | 核心 | acquire/release/refresh_unit/guard_turn/idle_evict；进程级 singleton；`execution_cache_created` / `execution_cache_reuse` 以 WARNING 写入 backend.log（供 Chrome E2E 断言） |
| `types.py` | 核心 | `ExecutionMode`、`BuiltExecutionUnit.teardown()` |
| `fingerprint.py` | 核心 | `compute_execution_fingerprint`（MCP/skill version/harness epoch） |
| `unit_ops.py` | 核心 | capture/apply/detach wrapper ↔ unit |
| `session_lifecycle.py` | 核心 | `resolve_execution_mode`、`finalize_agent_session`（release 前 refresh_unit） |

测试：`tests/services/agent/execution_cache/`（registry 单测 + stream_pipeline 集成测 2msg1build）。Chrome WebUI E2E：`tests/e2e/test_execution_cache_chrome_e2e.py`（`scripts/dev/lib/cdp_chat_ui.py` + CDP `json/new` 新 tab；前置 `./myrm ready --chrome` + backend log 断言 cache）。

---

## 模式

| 入口 | execution_mode | 行为 |
|------|----------------|------|
| WebUI / Channel / Wakeup | POOLED | 同 chat 复用 BuiltExecutionUnit |
| Cron / Eval / Kanban | EPHEMERAL | 每条消息 build + close |

删 chat：`chat_crud` 调用 `close_execution_cache_for_chat_all_agents`。
