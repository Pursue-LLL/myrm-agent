# channels/providers/

## 架构概述

多平台 IM Provider 注册表与共享基础设施。上级文档：[../_ARCH.md](../_ARCH.md)。

## 命名约定

| 前缀 | 含义 | 示例 |
|------|------|------|
| `_` 开头目录/文件 | **共享库**（非独立渠道，供多个 Provider 复用） | `_ilink/`（WeChat iLink 协议）、`_http_timeout.py`、`_twilio_utils.py` |
| 小写目录名 | **独立渠道 Provider** 包 | `discord/`、`feishu/`、`telegram/` |

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Channel providers — concrete channel implementations. | ✅ |
| `_http_timeout.py` | 模块 | app.channels.providers._http_timeout — Shared HTTP timeout resolution for channel API clients. | ✅ |
| `_twilio_utils.py` | 模块 | Internal utility module. Shared by Twilio-based channels (SMS, Voice) to avoid duplicating signature verification logic. | ✅ |
| `email/` | 包 | Email channel (IMAP inbound + SMTP outbound). Attachment/forwarded-mail parsing, HTML-to-Markdown cleaning, thread tracking. See `email/_ARCH.md`. | ✅ |
| `github/` | 包 | GitHub webhook channel. Inbound Issue/PR/Push/Review events via X-Hub-Signature-256 verified webhooks; outbound comments via REST API. See `github/_ARCH.md`. | ✅ |
| `imessage/` | 包 | iMessage channel via BlueBubbles API. Quoted replies, Tapback reactions, typing indicator, webhook auto-registration, read receipts, structured diagnostics. Submodules: channel.py, helpers.py, parser.py, webhook.py. | ✅ |
| `irc.py` | 模块 | IRC channel implementation. Raw asyncio TCP connection, supports SSL/TLS, NickServ authentication, nick collision auto-recovery, control character filtering, ou | ✅ |
| `registry.py` | 模块 | Channel provider registry — lazy-loading, thread-safe, zero overhead for unused channels. | ✅ |
| `sms.py` | 模块 | SMS channel provider. Sends/receives text messages via Twilio. Inbound via webhook, outbound via REST API. Pure text (no markdown). | ✅ |
| `voice_channel.py` | 模块 | Voice/phone call channel. Twilio ConversationRelay WebSocket protocol. Framework layer is WebSocket-library-agnostic — business layer injects receive/send funct | ✅ |
| `webhook.py` | 模块 | Generic webhook push channel. Converts OutboundMessage to JSON POST to user-specified URL. Suitable for third-party integrations like n8n, Zapier, or platforms. Reasoning payload is security-default OFF and requires explicit `metadata.webhook_include_reasoning=true` opt-in. | ✅ |
| `wechat/` | 包 | WeChat channel via iLink protocol. QR code login (AsyncLoginProtocol), bidirectional text/media messaging, typing indicator, multi-account support. See `wechat/_ARCH.md`. | ✅ |
| `whatsapp/` | 包 | WhatsApp channel via whatsapp-web.js Node bridge. QR code pairing (AsyncLoginProtocol), bidirectional text/media/reaction messaging, presence sync. See `whatsapp/_ARCH.md`. | ✅ |
| `_ilink/` | 共享库 | WeChat iLink HTTP protocol client. QR code fetch/poll, message send/receive, media upload/download, silk audio conversion. Used by `wechat/`. See `_ilink/_ARCH.md`. | ✅ |
| `zalo.py` | 模块 | Zalo Official Account channel. Supports bidirectional text/image/file messaging, getoa health check, and collect_issues diagnostics. | ✅ |

## 出站契约（所有 Provider 的 `send()`）

| 规则 | 说明 |
|------|------|
| 成功才返回 | 只有平台确认接受后才正常返回平台消息 id；未连接、无收件人、平台拒绝一律抛 `ChannelSendError`，`except` 内不得 `return None`。 |
| id 声明 | 平台不回传消息 id 的渠道声明 `ChannelCapabilities.message_ids=False`：DingTalk、IRC、VoiceCall、WeChat iLink、WeChat 公众号、企业微信智能机器人、企业微信应用、Webhook。其余渠道返回 `None` 视为未确认（纯媒体消息豁免）。 |
| 先文本后附件 | 附件逐个独立尝试（`../core/attachment_delivery.py` 的 `attempt_attachments` / `deliver_attachments`），一个失败不阻塞其余；LINE 例外：单次请求，媒体消息在前。 |
| 失败具名上报 | 附件失败汇总为一次 `ChannelSendError.for_attachments`：文本或其他附件已送达则 `accepted=True` 并列出 `failed_attachments`，由总线只重投未送达部分；否则按失败性质决定是否重试。 |
| 永久 vs 临时 | 仅"重试不可能改变结果"的失败判永久：类型不支持、本地文件缺失/不可读/为空、无可用来源、平台校验拒绝（`ChannelSendError.from_http_status` 对 4xx 同理，408/425/429/5xx 为临时）。URL 下载失败与网络错误按临时失败重试。 |
| 不静默丢弃 | 不支持的附件不得被悄悄略过；永久失败由总线剥离媒体并向收件人发本地化说明。 |
| 能力即行为 | `capabilities.media` / `file_upload` 必须与真实发送行为一致，`downgrade_components` 据此剥离。 |

守卫测试：`tests/channels/providers/test_send_contract.py`（`message_ids` 声明与 `send()` 内不吞错）。已知局限：多段文本中途失败不标记 `accepted`，重试会重发已送达的段（宁重复不缺失）；WhatsApp 桥接对媒体无送达回执。
