# channels/types/ 模块架构

## 架构概述

渠道域纯类型定义（无 I/O）：消息信封、会话策略、通知模式、UI 组件与 ReplyContext 结构化引用。Reply/Quote 协议详见 [REPLY_CONTEXT_DESIGN.md](REPLY_CONTEXT_DESIGN.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 类型包导出 | — |
| `messages.py` | 核心 | 跨渠道消息数据结构（MediaType: IMAGE/DOCUMENT/AUDIO/VIDEO/CONTACT, MediaAttachment（`ephemeral`=临时文件由消息总线在送达终态后删除）, guess_media_type, RenderStyle 等；`OutboundMessage.to_dict/from_dict` 为持久化线格式，每个嵌套 dataclass 都带 `__type__` 标签） | ✅ |
| `inbound_wire.py` | 核心 | `InboundMessage` 线格式的 TypedDict 声明（`InboundWire` 及嵌套 `ContextEntryWire`/`ReplyContextWire`）与编解码 `inbound_to_wire` / `inbound_from_wire`：入站日志持久化的就是它，重放回来的是用户发来的那条消息（附件、引用回复、群上下文、`resume_value` 都在）；`channel_capabilities` 由回合开始时的在线渠道重新取得，不持久化；字段集与 dataclass 的一致性、全部字段（除 `channel_capabilities`）逐一往返由 `tests/channels/types/test_inbound_wire.py` 守卫 | ✅ |
| `outbound_wire.py` | 核心 | `OutboundMessage` 线格式的 TypedDict 声明（`OutboundWire` 及嵌套 `ComponentWire`/`MediaWire` 等），让 `from_dict` 在类型层面可校验；字段集与 dataclass 的一致性由 `tests/channels/types/test_outbound_wire_shapes.py` 守卫 | ✅ |
| `topics.py` | 核心 | 话题路由类型（TopicContext、ReplyMode、DraftTimeoutAction、IdentityScopeMode）与 `METADATA_ROUTE_AGENT_KEY`（别名命令把回合路由到哪个智能体的消息元数据键） | ✅ |
| `streaming.py` | 核心 | Agent 执行流事件（ProgressUpdate、StreamingText、FissionTopologyNode/Update）与 `ApprovalExpiry`（工具审批的等待时长与超时决定，经 `ProgressUpdate.expiry` 交给路由器起计时器）、`METADATA_APPROVAL_WINDOW_SECONDS_KEY`（入站消息 metadata 里设定该回合审批等待时长的键，委托运行用它把等待放宽到任务时限）；审批提示还带提问回合的渠道会话键（`ProgressUpdate.session_key`），路由器随未决请求保存，续跑消息经 `METADATA_RESUME_SESSION_KEY` 带回，让答复接回提问回合的聊天 | ✅ |
| `voice.py` | 核心 | 语音 STT/TTS 配置与结果（VoiceConfig、TTSMode、STTResult） | ✅ |
| `components.py` | 核心 | 跨渠道交互组件（按钮、快捷回复等）类型 | ✅ |
| `session.py` | 核心 | 会话标识与隔离策略 | ✅ |
| `notification.py` | 核心 | 通知模式枚举与显式 @ 元数据 | ✅ |
| `context_document.py` | 核心 | 渠道随一次 turn 附带的参考文档：`ContextDocument`（正文 Markdown 或纯文本 + `ContextDocumentStatus`：READY/DENIED（应用没被加进这篇文档）/SCOPE_MISSING（应用根本没有读文档的权限）/TOO_LARGE/UNSUPPORTED/UNAVAILABLE；`clamped` 截断、`as_metadata`/`from_metadata` 经 `InboundMessage.metadata[METADATA_CONTEXT_DOCUMENT_KEY]` 往返）。生产方是能读取消息所指文档的 provider，消费方是智能体执行器 | ✅ |
| `status.py` | 核心 | 渠道状态与诊断类型：`ChannelStatus`、`StartMode`、`ChannelHealth`（熔断）、`ChannelActivity`（最近出入站时间，供 status API 消费）、`ChannelIssue`、`ChannelCapabilities`（`reaction_glyphs` 声明平台接受的反应表情，`None` 表示不限；`reaction_key` 去掉变体选择符）| ✅ |
| `thread_sharing.py` | 核心 | 话题级 thread 共享/隔离模式 | ✅ |
