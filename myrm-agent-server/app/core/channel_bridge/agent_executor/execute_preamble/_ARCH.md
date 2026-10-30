# core/channel_bridge/agent_executor/execute_preamble/

## 架构概述

Preamble 子包：InboundMessage → GeneralAgent 的执行前置编排（预算门控、会话键、历史、Agent 装配、指令富化）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | preamble 域门面：聚合导出各子模块对外能力。 | ✅ |
| `preamble.py` | 核心 | Preamble 编排门面：预算门控 + 子模块串联。记忆范围确定后，所有者私聊的非续跑回合把本条消息登记为该会话的 IM 来源（`wake_return.get_wake_origins`），唤醒回合的回复据此回到这条私聊；群聊与访客回合在记忆隔离舱里运行，不登记——唤醒回合带着所有者的全部记忆，回复不能进入被这份记忆隔开的对话。 | ✅ |
| `types.py` | 模块 | preamble 数据结构（`query_input` 为文本、多模态块列表或 resume `Command`；`ChannelExecutionPrep.session_key` 是本回合所在的渠道会话键，审批卡据此写明提问回合的会话）；`ChannelAgentBuildOutcome` XOR（result | early_reply）与安全配置组装（`build_security_config`：用户配置 + 本回合消息设定的审批等待时长 + YOLO 状态；委托运行的审批等待取任务时限）。 | ✅ |
| `session.py` | 模块 | 会话键、冷启动检测、历史加载、auto-reset 预事件。审批续跑回合（`METADATA_RESUME_SESSION_KEY`）不重算会话键，沿用提问回合的会话：不落库、不 backfill、不做冷启动检测、不播报 reset；该会话的聊天已不存在时回一条标记为失败回合的说明（`approval_session_gone`）。没有该键的续跑（路由器没有持有对应请求的答复）仍按本条消息自己的会话解析。 | ✅ |
| `agent.py` | 模块 | `build_channel_execution_agent()`：Params 装配、resume 门控（人工续跑认领审批键；路由器因超时发起的续跑已由计时器认领，因此不重复认领；Agent 装配或凭证注入失败时重开该键，重试不被当成已处理）、凭证注入；团队身份作用域解析（`ident:<id>` 记忆域 + 个人/共享凭证双轨 + 冻结回退默认智能体）；群聊 / 访客 / 配对成员 turn 经 `resolve_turn_memory_scope` 使用记忆 compartment（读域 `conversation` + `ident:<稳定 id>`，写入落 `ident:`，关闭 L3 抽取与 conversation_search，owner 私有记忆不进入这些 turn；`preamble.py` 把 `untrusted_sender` 传入）；text-only 主模型 + visionFallback 时对入站多模态 query 调用 `preprocess_inbound_multimodal_query` 并发送 `analyzing_image` ProgressUpdate；/learn turn 经 `apply_learn_skill_manage_permission_overlay` 对齐 skill_manage 权限，`force_skill_manage` 与之共用 `learn_authoring_prompt_text`（纯文本与多模态块列表同一判定口径）。 | ✅ |
| `context_document.py` | 模块 | `attach_context_document()`：把渠道随 turn 附带的参考文档（`InboundMessage.metadata` 的 `ContextDocument`）追加到本轮 text query 末尾——可读时经 `wrap_tool_output` 边界内联；超过 harness 默认阈值（>16,000 字符或词元压力 >8,000，低于人写文本的停车线：这是第三方文本）则存进 `agent_workspace()` 的 `.myrm/spillover` 文件并只给出路径与 `file_read_tool` 指引（不带预览）；读不到时给出一句不含技术细节的缺失说明（区分文档没授权与应用没有读文档权限），让模型据实回答；可读正文都带一句「表格、嵌入表格、白板和图片可能缺失或被拍平」的提醒，避免模型把缺失当作文档里没有。只作用于 live turn：持久化历史与 `params.query` 不含文档，resume 不重复附带 | ✅ |
| `replay_notice.py` | 模块 | `attach_replay_notice()`：重启后重放的消息（`is_recovered()`）在本轮 query 末尾并入一句重放提示——消息在重启前到达、可能已部分处理，要对聊天之外有影响的步骤（发消息、写文件、跑命令、调外部服务）先核对是否已做过再重复，然后继续处理请求；字符串 query 直接追加，多模态 query 并入其文本部分（图片原样保留），没有文本部分时补一段；普通消息原样不变。重放消息就是用户发来的那条，没有提示时模型分不出它与新请求，会重复中断的那一轮已执行的步骤。提示只在 live turn 出现，持久化历史与 `params.query` 保持用户原文；审批答复的重放走 resume，不带 query 文字，不加。 | ✅ |
| `instructions.py` | 模块 | 团队协议、渠道能力约束、IM 行为策略 Persona、`profile_output_suffixes`（人格 + response_locale_policy）注入 `user_instructions` 尾。 | ✅ |
| `backfill.py` | 模块 | 冷启动渠道历史 backfill（`maybe_backfill_channel_history`）。 | ✅ |

## 测试

- `tests/core/channel_bridge/test_execute_preamble_wake_origin.py` — 所有者私聊回合登记 IM 来源；群聊、访客、续跑、会话打不开的回合不登记
- `tests/core/channel_bridge/test_execute_preamble_early_exit.py` — preamble 早退与 resume 认领（resume timeout、超时续跑不重复认领、装配失败重开审批键、search unavailable、Outcome XOR）
- `tests/core/channel_bridge/test_execute_preamble_security_config.py` — 回合安全配置：回合审批等待覆盖配置值且不改动入参，非正数/布尔/非数值被忽略，与 YOLO 状态并存
- `tests/core/channel_bridge/test_enrich_preamble_instructions.py` — IM Persona 注入触发/非触发验证
- `tests/core/channel_bridge/test_execute_preamble_context_document.py` — 参考文档并入 live turn：内联/外溢进智能体工作区（真实文件往返）/各缺失原因/截断标注/边界标记不可伪造；resume 与多模态 query 不并入；`params.query` 不含文档
- `tests/core/channel_bridge/test_execute_preamble_replay_notice.py` — 重放提示：字符串与多模态 query（图片保留、入参不被改动、无文本部分时补一段）、非重放与标志为假的消息原样不变；经 `build_channel_execution_agent` 只出现在 live turn（`params.query` 仍是用户原文），审批答复的重放不加
- `tests/core/channel_bridge/preamble_testkit.py` — preamble 测试共用的构建器：`inbound_message()`、`minimal_user_configs()`、`build_agent()`（除变化项外其余参数取朴素默认值）、`build_live_turn()`（装配出的回合与创建智能体所用的 params）
