# core/channel_bridge/agent_executor/

## 架构概述

渠道入站消息 → GeneralAgent 执行桥。上级文档：[../../_ARCH.md](../../_ARCH.md)。
根目录保留门面与单文件域；多文件域收进 `deliverable/` 与 `execute_preamble/` 子包。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Business-layer AgentExecutor for channel inbound messages. | ✅ |
| `executor.py` | 核心 | ChannelAgentExecutor orchestration：FAQ 语义拦截 → preamble 调度 → stream → finally。topic_context.agent_id 存在且非 resume 时，先尝试 `_try_faq_intercept`，命中则直接 yield OutboundMessage 并跳过 Agent 管线。 | ✅ |
| `execute_finalize.py` | 模块 | 流结束后 persist + metadata + media + artifact 深链 reply 组装；超限交付物压缩/提示拼接（线程池执行路径扫描）；深链成功时抑制对应超限提示（兜底：深链失败提示保留）；空内容但存在交付物（按钮/附件）时回退交付文案。 | ✅ |
| `execute_errors.py` | 模块 | ConfigIncomplete / MyrmLLM / 通用异常 → OutboundMessage 回复。 | ✅ |
| `stream_events.py` | 模块 | harness `process_stream` 事件 → ProgressUpdate/StreamingText 映射；`capability_gap` + `reason=surface_unavailable` 或 `web_search` + `not_configured`/`unreachable` → ProgressUpdate(display_message)；审批超时 side-effect 状态。 | ✅ |
| `helpers.py` | 模块 | 入站 query 组装：`build_channel_inbound_query`（含 reply context、group context、document blocks、contact cards、forwarded email context、multimodal images）、memory identity 解析、delivery provenance banner。 | ✅ |
| `session.py` | 模块 | Build a structured session key (base, without epoch). Exports `build_channel_budget_key(msg)` for channel budget guard key construction (single source of truth for peer resolution). | ✅ |
| `execute_preamble/` | 子包 | InboundMessage → GeneralAgent 执行前置编排。门面 `__init__.py` 聚合导出。 | [execute_preamble/_ARCH.md](execute_preamble/_ARCH.md) |
| `deliverable/` | 子包 | IM 渠道超限交付物统一处理（附件上限/压缩/路径扫描/深链）。门面 `__init__.py` 聚合导出。 | [deliverable/_ARCH.md](deliverable/_ARCH.md) |

## 测试

- `tests/core/channel_bridge/test_deliverable_deep_links.py` — artifact 收集、超限深链/压缩/提示三态、深链失败提示兜底与深链构建
- `tests/core/channel_bridge/test_execute_finalize.py` — finalize 深链成功抑制提示 / 失败保留提示 / 压缩提示恒保留 / 空内容交付文案回退
- `tests/core/channel_bridge/test_deliverable_scanner.py` — 路径扫描、超限压缩/提示与文本剥离
- `tests/core/channel_bridge/test_deliverable_media.py` — 附件大小上限格式化与渐进压缩（透明保留、失败回退）
- `tests/core/channel_bridge/test_stream_events.py` — harness 流事件映射
- `tests/core/channel_bridge/test_execute_preamble_early_exit.py` — preamble 早退（resume timeout、search unavailable、Outcome XOR）
- `tests/core/channel_bridge/test_enrich_preamble_instructions.py` — IM Persona 注入触发/非触发验证
- `tests/core/channel_bridge/test_channel_inbound_user_text.py` — 入站 query 组装（banner、reply context、group context、multimodal、forwarded email context）
