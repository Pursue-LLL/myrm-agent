# core/channel_bridge/agent_executor/execute_preamble/

## 架构概述

Preamble 子包：InboundMessage → GeneralAgent 的执行前置编排（预算门控、会话键、历史、Agent 装配、指令富化）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | preamble 域门面：聚合导出各子模块对外能力。 | ✅ |
| `preamble.py` | 核心 | Preamble 编排门面：预算门控 + 子模块串联。 | ✅ |
| `types.py` | 模块 | preamble 数据结构；`ChannelAgentBuildOutcome` XOR（result | early_reply）与安全配置组装。 | ✅ |
| `session.py` | 模块 | 会话键、冷启动检测、历史加载、auto-reset 预事件。 | ✅ |
| `agent.py` | 模块 | `build_channel_execution_agent()`：Params 装配、resume 门控、凭证注入；text-only 主模型 + visionFallback 时对入站多模态 query 调用 `preprocess_inbound_multimodal_query` 并发送 `analyzing_image` ProgressUpdate；/learn turn 经 `apply_learn_skill_manage_permission_overlay` 对齐 skill_manage 权限。 | ✅ |
| `instructions.py` | 模块 | 团队协议、渠道能力约束、IM 行为策略 Persona、`profile_output_suffixes`（人格 + response_locale_policy）注入 `user_instructions` 尾。 | ✅ |
| `backfill.py` | 模块 | 冷启动渠道历史 backfill（`maybe_backfill_channel_history`）。 | ✅ |

## 测试

- `tests/core/channel_bridge/test_execute_preamble_early_exit.py` — preamble 早退（resume timeout、search unavailable、Outcome XOR）
- `tests/core/channel_bridge/test_enrich_preamble_instructions.py` — IM Persona 注入触发/非触发验证
