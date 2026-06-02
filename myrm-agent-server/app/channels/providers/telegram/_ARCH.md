# telegram/

## Overview
Telegram channel provider — Bot API bidirectional messaging with Forum Topic management.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Telegram channel provider — Bot API bidirectional messaging. | — |
| api.py | Core | Telegram Bot API async HTTP client with endpoint fallback. Covers messaging, media, commands, reactions, and Forum Topic CRUD (Bot API 6.3+). | ✅ |
| channel.py | Core | Telegram Bot channel implementation. DM/group chat, media groups, draft streaming, Forum Topic management (create/rename/close/reopen), auto-topic creation with per-user dedup locking and name sync. | ✅ |
| constants.py | Core | Telegram Bot API constants and limits. | ✅ |
| exceptions.py | Core | Telegram-specific exceptions for file size validation and API errors. | ✅ |
| helpers.py | Core | Telegram module-level utility functions, constants, and data structures. `send_media_attachment` routes media with optional notification kwargs. | ✅ |
| html_converter.py | Core | Markdown to Telegram HTML converter. Handles bold/italic/strikethrough/code/link. Preserves Telegram-supported HTML tags (blockquote expandable, etc.) during escape. | ✅ |
| inbound.py | Core | Telegram inbound message parsing, polling loop with intelligent error classification (409 Conflict detection + DEGRADED state feedback), media group aggregation mixin, and `_pre_emit_hook` extensibility point. `_message_mentions_bot` scans text/caption entities (mention, text_mention, bot_command); `_strip_bot_mention_text` cleans group trigger content; sets `explicit_mention` metadata for guest gating. | ✅ |
| models.py | Core | Pydantic models for Telegram Bot API webhook payloads (TgUser, TgChat, TgLocation, TgVenue, TgMessage with `caption_entities`, TgUpdate, etc.). | ✅ |
| notification.py | Core | Telegram `disable_notification` kwargs builder for important/all notification modes. | ✅ |
