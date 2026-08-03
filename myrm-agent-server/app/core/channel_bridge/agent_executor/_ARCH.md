# core/channel_bridge/agent_executor/

## 架构概述

渠道入站消息 → GeneralAgent 执行桥。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Business-layer AgentExecutor for channel inbound messages. | ✅ |
| `executor.py` | 核心 | ChannelAgentExecutor orchestration：FAQ 语义拦截 → preamble 调度 → stream → finally。topic_context.agent_id 存在且非 resume 时，先尝试 `_try_faq_intercept`，命中则直接 yield OutboundMessage 并跳过 Agent 管线。 | ✅ |
| `execute_preamble.py` | 模块 | Preamble 编排门面：预算门控 + 子模块串联。 | ✅ |
| `execute_preamble_types.py` | 模块 | preamble 数据结构；`ChannelAgentBuildOutcome` XOR（result | early_reply） | ✅ |
| `execute_preamble_session.py` | 模块 | 会话键、冷启动检测、历史加载、auto-reset 预事件。 | ✅ |
| `execute_preamble_agent.py` | 模块 | `build_channel_execution_agent()`：Params 装配、resume 门控、凭证注入；text-only 主模型 + visionFallback 时对入站多模态 query 调用 `preprocess_inbound_multimodal_query` 并发送 `analyzing_image` ProgressUpdate；/learn turn 经 `apply_learn_skill_manage_permission_overlay` 对齐 skill_manage 权限。 | ✅ |
| `execute_preamble_instructions.py` | 模块 | 团队协议、渠道能力约束、IM 行为策略 Persona、人格模板注入 `user_instructions`。 | ✅ |
| `execute_preamble_backfill.py` | 模块 | 冷启动渠道历史 backfill（`maybe_backfill_channel_history`）。 | ✅ |
| `execute_finalize.py` | 模块 | 流结束后 persist + metadata + media + artifact 深链 reply 组装。 | ✅ |
| `execute_errors.py` | 模块 | ConfigIncomplete / MyrmLLM / 通用异常 → OutboundMessage 回复。 | ✅ |
| `artifact_deep_links.py` | 模块 | 可分享 artifact 的 IM 附件收集 + HMAC 深链 ActionButton 生成 + DB version 批量查询。 | ✅ |
| `deliverable_path_scanner.py` | 模块 | Channel 回复正文 workspace 路径扫描 → IM 原生附件（跳过 code block/inline code；workspace 沙箱内解析）。 | ✅ |
| `stream_events.py` | 模块 | harness `process_stream` 事件 → ProgressUpdate/StreamingText 映射；`capability_gap` + `reason=surface_unavailable` 或 `web_search` + `not_configured`/`unreachable` → ProgressUpdate(display_message)；审批超时 side-effect 状态。 | ✅ |
| `helpers.py` | 模块 | 入站 query 组装：`build_channel_inbound_query`（含 reply context、group context、document blocks、contact cards、forwarded email context、multimodal images）、memory identity 解析、delivery provenance banner。 | ✅ |
| `session.py` | 模块 | Build a structured session key (base, without epoch). Exports `build_channel_budget_key(msg)` for channel budget guard key construction (single source of truth for peer resolution). | ✅ |

## 测试

- `tests/core/channel_bridge/test_artifact_deep_links.py` — artifact 收集与深链
- `tests/core/channel_bridge/test_stream_events.py` — harness 流事件映射
- `tests/core/channel_bridge/test_execute_preamble_early_exit.py` — preamble 早退（resume timeout、search unavailable、Outcome XOR）
- `tests/core/channel_bridge/test_enrich_preamble_instructions.py` — IM Persona 注入触发/非触发验证
- `tests/core/channel_bridge/test_channel_inbound_user_text.py` — 入站 query 组装（banner、reply context、group context、multimodal、forwarded email context）
