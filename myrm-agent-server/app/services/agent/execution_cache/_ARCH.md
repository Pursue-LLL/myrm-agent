# execution_cache 模块

---

## 架构概述

Chat 级 `BuiltExecutionUnit` 池（SkillAgent + BrowserSession）。WebUI/Channel/Wakeup 走 POOLED；Cron/Eval/Kanban 走 EPHEMERAL。镜像 `ChatRuntimePoolRegistry` 生命周期语义。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 公共导出 | ✅ |
| `registry.py` | 核心 | acquire/release/refresh_unit/guard_turn/idle_evict；`snapshot_warm_units` / `is_scope_turn_active` 供 catalog 热更新；进程级 singleton | ✅ |
| `types.py` | 核心 | `ExecutionMode`、`BuiltExecutionUnit.teardown()` | ✅ |
| `fingerprint.py` | 核心 | `compute_execution_fingerprint`（模型类字段统一经 `_model_sig` 提取 build 固化签名，含主/兜底/推理/轻量/视觉/视频模型与隐私路由；技能/MCP/harness epoch/`engine_params` 含 MoA preset 激活态/安全配置/记忆配置/执行网络/通知/看板/子代理/委托——覆盖所有 build 期固化的用户可配置输入；排除 api_key 等凭据池字段、每 run 状态与全局静态配置） | ✅ |
| `unit_ops.py` | 核心 | capture/apply/detach wrapper ↔ unit | ✅ |
| `session_lifecycle.py` | 核心 | `resolve_execution_mode`、`finalize_agent_session`（release 前 refresh_unit） | ✅ |
| `prewarm/` | 核心 | Turn1 冷启动预热（见 [prewarm/_ARCH.md](prewarm/_ARCH.md)） | ✅ |

测试：`tests/services/agent/execution_cache/`（registry + fingerprint 全 build 配置 bust 覆盖 + prewarm coordinator）· `tests/api/agent/test_prewarm_api.py` · Chrome E2E `tests/e2e/test_execution_cache_chrome_e2e.py`（prewarm log + 2msg1build）。

---

## 模式

| 入口 | execution_mode | 行为 |
|------|----------------|------|
| WebUI / Channel / Wakeup | POOLED | 同 chat 复用 BuiltExecutionUnit |
| Cron / Eval / Kanban | EPHEMERAL | 每条消息 build + close |

删 chat：`chat_crud` 调用 `close_execution_cache_for_chat_all_agents`。
