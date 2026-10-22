# core/channel_bridge/agent_executor/

## 架构概述

渠道入站消息 → GeneralAgent 执行桥。上级文档：[../../_ARCH.md](../../_ARCH.md)。
根目录保留门面与单文件域；多文件域位于 `deliverable/` 与 `execute_preamble/` 子包。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Business-layer AgentExecutor for channel inbound messages. | ✅ |
| `executor.py` | 核心 | ChannelAgentExecutor orchestration（每次 `process_stream` 打开经 `track_background_agent_run` 计入 liveness `busy`，云托管空闲回收器据此不在 IM 对话中途暂停沙箱）：FAQ 语义拦截 → preamble 调度 → stream → finally。topic_context.agent_id 存在且非 resume 时，先尝试 `_try_faq_intercept`，命中则直接 yield OutboundMessage 并跳过 Agent 管线。回复附件的临时文件不在此清理（`ephemeral` 附件由消息总线在送达终态后删除，避免上传前被删）。 | ✅ |
| `execute_finalize.py` | 模块 | 流结束后 persist + metadata + media + artifact 深链 reply 组装；超限交付物压缩/提示拼接（线程池执行路径扫描）；深链成功时抑制对应超限提示（兜底：深链失败提示保留）；空内容但存在交付物（按钮/附件）时回退交付文案；截图与压缩图附件标记 `ephemeral`，被深链按钮取代而丢弃的临时附件立即释放；失败回合的回复是错误类型对应的成员安全文案加参考编号（`friendly_errors`，随成员语言，写入会话历史），提供方原始错误文本只按同一参考编号进运维日志；文字已流出后才失败时保留该文字，其后附同一条成员安全文案并带失败标记，半截回答不会被当成完整回答。 | ✅ |
| `execute_errors.py` | 模块 | ConfigIncomplete / MyrmLLM / 通用异常 → OutboundMessage 回复；失败回复的 `metadata[error_type]` 是失败回合标记。通用异常走 `build_generic_error_reply`：只回成员安全文案加参考编号（可信所有者私聊才附账户指引），原始异常按同一参考编号进日志。`MyrmLLMError` 异常只有可信所有者私聊走 `build_llm_error_reply`（诊断文案加恢复按钮），访客、配对成员与群聊同样走成员安全文案；harness 目前在 `agent_runtime.py` 吞掉该异常改发 error 事件，这条分支实际由流式失败回复（`execute_finalize`）覆盖。 | ✅ |
| `stream_events.py` | 模块 | harness `process_stream` 事件 → ProgressUpdate/StreamingText 映射；`capability_gap` + `web_search` + `not_configured`/`unreachable` → ProgressUpdate(display_message)；审批超时 side-effect 状态；回复文本经 `acc.draft`（`AnswerDraft`）累积，模型切换等恢复重放时只丢在途段落、不把半截文字与重发的整段拼在一起；致命 `error` 事件把原始文本（运维日志用）与 `error_kind`（成员文案用，未知值按 UNKNOWN）记到累积器。 | ✅ |
| `helpers.py` | 模块 | 入站 query 组装：`build_channel_inbound_query`（含 reply context、group context、document blocks、contact cards、forwarded email context、multimodal images）、memory identity 解析、delivery provenance banner。 | ✅ |
| `session.py` | 模块 | Build a structured session key (base, without epoch). Exports `build_channel_budget_key(msg)` for channel budget guard key construction (single source of truth for peer resolution) and `build_channel_session_key(msg)` for callers that must look up the ``Chat`` row by the exact ``channel_session_key`` this layer stores (channel + peer_kind + peer + topic + agent). | ✅ |
| `execute_preamble/` | 子包 | InboundMessage → GeneralAgent 执行前置编排。门面 `__init__.py` 聚合导出。 | [execute_preamble/_ARCH.md](execute_preamble/_ARCH.md) |
| `deliverable/` | 子包 | IM 渠道超限交付物统一处理（附件上限/压缩/路径扫描/深链）。门面 `__init__.py` 聚合导出。 | [deliverable/_ARCH.md](deliverable/_ARCH.md) |

## 测试

- `tests/core/channel_bridge/test_deliverable_deep_links.py` — artifact 收集、超限深链/压缩/提示三态、深链失败提示兜底与深链构建
- `tests/core/channel_bridge/test_execute_finalize.py` — finalize 深链成功抑制提示 / 失败保留提示 / 压缩提示恒保留 / 空内容交付文案回退 / 截图临时文件交接与被取代附件释放
- `tests/core/channel_bridge/test_execute_finalize_errors.py` — 失败回合按错误类型回复成员安全文案加参考编号、不泄露提供方原文与账单状态、随成员语言、原文按同一参考编号进日志、已流出的文字保留并附失败文案与标记（复用 `test_execute_finalize._finalize`）；失败回复带失败回合标记、账户指引只在传入时替换文案
- `tests/core/channel_bridge/test_executor_error_replies.py` — 通用异常只回成员安全文案加参考编号并带失败标记、原始异常按同一参考编号进日志；可信所有者私聊得到账户指引，访客、配对成员与群聊只得通用文案（含 BYOK 与托管计费措辞的区别）；`MyrmLLMError` 诊断只到所有者私聊
- `tests/core/channel_bridge/test_executor_faq_reply.py` — FAQ 命中的回答原样回到提问的会话（回复关联到原消息）
- `tests/core/channel_bridge/test_deliverable_scanner.py` — 路径扫描、超限压缩/提示与文本剥离
- `tests/core/channel_bridge/test_deliverable_media.py` — 附件大小上限格式化与渐进压缩（透明保留、失败回退）
- `tests/core/channel_bridge/test_stream_events.py` — harness 流事件映射；致命错误事件的原始文本与错误类型记录（后一条错误覆盖前一条、缺失或未知的类型按 UNKNOWN）；模型切换重放替换半截回答、工具步骤之前的文字保留
- `tests/core/channel_bridge/test_execute_preamble_early_exit.py` — preamble 早退（resume timeout、search unavailable、Outcome XOR）
- `tests/core/channel_bridge/test_enrich_preamble_instructions.py` — IM Persona 注入触发/非触发验证
- `tests/core/channel_bridge/test_channel_inbound_user_text.py` — 入站 query 组装（banner、reply context、group context、multimodal、forwarded email context）
