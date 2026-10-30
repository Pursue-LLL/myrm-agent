# channels/providers/telegram/

## 架构概述

Telegram 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Telegram channel provider — Bot API bidirectional messaging. | ✅ |
| `api.py` | 模块 | Telegram Bot API async HTTP client. `TelegramClient` composes the media and forum-topic groups and holds the text, interaction, command, webhook and rich-message calls. | ✅ |
| `api_core.py` | 模块 | Transport shared by every method group: one endpoint (official host or an `api_base` override), an optional forward `proxy` (`http://`, `https://`, `socks5://`, `socks5h://`; surrounding whitespace is dropped; without it the process environment decides) for every call and file download, the pooled `httpx.AsyncClient`, the unified `_call`, and `TelegramApiError` (`is_invalid_token` marks a refused bot token, `is_method_not_found` an unknown method). A transport error reaches the caller as the `httpx` error it is, so the retry policy can tell a connection that never opened from a request the platform may already hold. | ✅ |
| `api_media.py` | 模块 | Media group of the client: photo, document, voice, audio and video uploads through one `_send_media`, file download through `getFile`, and `get_recommended_send_method`. | ✅ |
| `api_forum.py` | 模块 | Forum Topic group of the client: create, rename, close, reopen and delete topics. | ✅ |
| `channel.py` | 模块 | Telegram Bot channel core: credentials (`botToken`, `webhookUrl`, `botPolicy`, `autoTopic`, `notificationsMode` and the optional `proxy` handed to the client), lifecycle, diagnostics, mixin composition. | ✅ |
| `outbound.py` | 模块 | Outbound messaging mixin: send (HTML parts through `deliver_chunks`), edit, draft preview, react, pin; delegates Rich send to outbound_rich. | ✅ |
| `outbound_rich.py` | 模块 | Rich Message send mixin: sendRichMessage with HTML fallback on capability or parse errors of the first part; later parts go through `deliver_chunks`, so one that fails is a partial delivery, not a fallback. | ✅ |
| `topics.py` | 模块 | Forum Topic mixin: create/rename/close/reopen, auto-topic per user, name sync. | ✅ |
| `hooks.py` | 模块 | Pre-emit hook mixin: /agent command, inline agent picker, auto-topic routing. | ✅ |
| `webhook.py` | 模块 | Webhook mixin: signature verify, setWebhook lifecycle, POST /webhook route on a route registrar (any other object is ignored with a warning). | ✅ |
| `constants.py` | 模块 | Telegram Bot API constants and limits, and `TELEGRAM_REACTION_EMOJI`: the 73 emoji a bot may set as a reaction (anything else is `REACTION_INVALID`). | ✅ |
| `exceptions.py` | 模块 | Telegram-specific exceptions for file size validation and API errors. | ✅ |
| `helpers.py` | 模块 | Telegram module-level utility functions, constants (polling timings, `_ALLOWED_UPDATES` shared by polling and webhook) and data structures. | ✅ |
| `html_converter.py` | 模块 | Markdown to Telegram HTML converter. GFM table degradation, 4096-char HTML-aware splitting with bare CJK punctuation breakpoints (`CJK_BOUNDARY_CHARS` from splitter), Rich Message splitting (32768 UTF-8). | ✅ |
| `inbound.py` | 模块 | Inbound update dispatch and media-group aggregation mixin: message and edited_message dispatch, callback_query (qr/act/sel/ag) and message_reaction conversion, media-group debounce plus hard deadline. | ✅ |
| `inbound_message.py` | 模块 | Message conversion mixin: text, caption, photo, document, video, video_note, voice, sticker, contact, venue and location content, the replied-to message context, group mention detection (sets `explicit_mention` for guest-mode gating) and mention stripping. | ✅ |
| `inbound_poll.py` | 模块 | Long-polling mixin: the getUpdates loop, 409 Conflict handling (limited retries, then ERROR) and exponential backoff with DEGRADED status for network errors. | ✅ |
| `models.py` | 模块 | Pydantic models for Telegram Bot API webhook payloads (TgUser, TgChat, TgMessage, TgVideoNote, TgContact, etc.). | ✅ |
| `notification.py` | 模块 | Telegram `disable_notification` helpers (`all` notifies for every message, `important` silences the rest) and the `NotificationKwargs` type every send call receives. | ✅ |
