# core/channel_bridge/agent_executor/execute_preamble/

## 架构概述

Preamble 子包：InboundMessage → GeneralAgent 的执行前置编排（预算门控、会话键、历史、Agent 装配、指令富化）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | preamble 域门面：聚合导出各子模块对外能力。 | ✅ |
| `preamble.py` | 核心 | Preamble 编排门面：预算门控 + 子模块串联。 | ✅ |
| `types.py` | 模块 | preamble 数据结构（`query_input` 为文本、多模态块列表或 resume `Command`）；`ChannelAgentBuildOutcome` XOR（result | early_reply）与安全配置组装。 | ✅ |
| `session.py` | 模块 | 会话键、冷启动检测、历史加载、auto-reset 预事件。 | ✅ |
| `agent.py` | 模块 | `build_channel_execution_agent()`：Params 装配、resume 门控（认领审批键；Agent 装配或凭证注入失败时重开该键，重试不被当成已处理）、凭证注入；团队身份作用域解析（`ident:<id>` 记忆域 + 个人/共享凭证双轨 + 冻结回退默认智能体）；群聊 / 访客 / 配对成员 turn 经 `resolve_turn_memory_scope` 使用记忆 compartment（读域 `conversation` + `ident:<稳定 id>`，写入落 `ident:`，关闭 L3 抽取与 conversation_search，owner 私有记忆不进入这些 turn；`preamble.py` 把 `untrusted_sender` 传入）；text-only 主模型 + visionFallback 时对入站多模态 query 调用 `preprocess_inbound_multimodal_query` 并发送 `analyzing_image` ProgressUpdate；/learn turn 经 `apply_learn_skill_manage_permission_overlay` 对齐 skill_manage 权限，`force_skill_manage` 与之共用 `learn_authoring_prompt_text`（纯文本与多模态块列表同一判定口径）。 | ✅ |
| `context_document.py` | 模块 | `attach_context_document()`：把渠道随 turn 附带的参考文档（`InboundMessage.metadata` 的 `ContextDocument`）追加到本轮 text query 末尾——可读时经 `wrap_tool_output` 边界内联；超过 `ContextBombDefenseService` 阈值则存进 `agent_workspace()` 的 `.myrm/spillover` 文件并只给出路径与 `file_read_tool` 指引（不带预览）；读不到时给出一句不含技术细节的缺失说明，让模型据实回答。只作用于 live turn：持久化历史与 `params.query` 不含文档，resume 不重复附带 | ✅ |
| `instructions.py` | 模块 | 团队协议、渠道能力约束、IM 行为策略 Persona、`profile_output_suffixes`（人格 + response_locale_policy）注入 `user_instructions` 尾。 | ✅ |
| `backfill.py` | 模块 | 冷启动渠道历史 backfill（`maybe_backfill_channel_history`）。 | ✅ |

## 测试

- `tests/core/channel_bridge/test_execute_preamble_early_exit.py` — preamble 早退与 resume 认领（resume timeout、装配失败重开审批键、search unavailable、Outcome XOR）
- `tests/core/channel_bridge/test_enrich_preamble_instructions.py` — IM Persona 注入触发/非触发验证
- `tests/core/channel_bridge/test_execute_preamble_context_document.py` — 参考文档并入 live turn：内联/外溢进智能体工作区（真实文件往返）/各缺失原因/截断标注/边界标记不可伪造；resume 与多模态 query 不并入；`params.query` 不含文档
