# channels/providers/telegram/

## 架构概述

Telegram 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Telegram channel provider — Bot API bidirectional messaging. | ✅ |
| `api.py` | 模块 | Telegram Bot API async HTTP client. Encapsulates all Bot API HTTP calls (messaging, media, commands, reactions, Forum Topic CRUD, voice/video download) with automatic endpoint fallback. | ✅ |
| `channel.py` | 模块 | Telegram Bot channel implementation. DM/group chat, media group debounce, webhook/polling dual mode, inline keyboard, Markdown→HTML, message splitting, /agent inline picker, Forum Topic management, voice/video file download. | ✅ |
| `constants.py` | 模块 | Telegram Bot API constants and limits. | ✅ |
| `exceptions.py` | 模块 | Telegram-specific exceptions for file size validation and API errors. | ✅ |
| `helpers.py` | 模块 | Telegram module-level utility functions, constants, and data structures. | ✅ |
| `html_converter.py` | 模块 | Markdown to Telegram HTML converter. Handles bold/italic/strikethrough/code/link/GFM table degradation (monospace ASCII), supports 4096-char message splitting with state-machine-based HTML tag auto-closing and Rich Message splitting (32768 UTF-8). | ✅ |
| `inbound.py` | 模块 | Telegram inbound message parsing, polling loop, and media group aggregation mixin. Supports message/edited_message/callback_query (qr/act/sel/ag)/sticker/location/venue/contact/video_note. Sets metadata for downstream enrichment. | ✅ |
| `models.py` | 模块 | Pydantic models for Telegram Bot API webhook payloads (TgUser, TgChat, TgMessage, TgVideoNote, TgContact, etc.). | ✅ |
| `notification.py` | 模块 | Telegram disable_notification helpers (Hermes-compatible important/all modes). | ✅ |
