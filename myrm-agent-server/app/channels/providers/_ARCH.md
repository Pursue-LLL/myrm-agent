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
| `email.py` | 模块 | Email channel implementation. Supports IMAP polling for inbox, SMTP sending, attachment parsing, and thread tracking. | ✅ |
| `imessage.py` | 模块 | iMessage channel via BlueBubbles API. Text/media send, Tapback reactions, webhook authentication, structured diagnostics. | ✅ |
| `irc.py` | 模块 | IRC channel implementation. Raw asyncio TCP connection, supports SSL/TLS, NickServ authentication, nick collision auto-recovery, control character filtering, ou | ✅ |
| `registry.py` | 模块 | Channel provider registry — lazy-loading, thread-safe, zero overhead for unused channels. | ✅ |
| `sms.py` | 模块 | SMS channel provider. Sends/receives text messages via Twilio. Inbound via webhook, outbound via REST API. Pure text (no markdown). | ✅ |
| `voice_channel.py` | 模块 | Voice/phone call channel. Twilio ConversationRelay WebSocket protocol. Framework layer is WebSocket-library-agnostic — business layer injects receive/send funct | ✅ |
| `webhook.py` | 模块 | Generic webhook push channel. Converts OutboundMessage to JSON POST to user-specified URL. Suitable for third-party integrations like n8n, Zapier, or platforms  | ✅ |
| `zalo.py` | 模块 | Zalo Official Account channel. Supports bidirectional text/image/file messaging, getoa health check, and collect_issues diagnostics. | ✅ |
