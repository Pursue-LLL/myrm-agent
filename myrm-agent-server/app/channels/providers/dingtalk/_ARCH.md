# dingtalk/

## Overview
DingTalk channel package — re-exports DingTalkChannel for registry.

Supports bidirectional messaging (Stream API WebSocket for inbound, OpenAPI for outbound)
and AI Card streaming for real-time typewriter-effect responses.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | DingTalk channel package — re-exports DingTalkChannel for registry. | — |
| api.py | Core | DingTalk OpenAPI client. Token management, messaging, media, AI Card streaming, and download code resolution APIs. | ✅ |
| channel.py | Core | DingTalk robot channel. Stream API WebSocket inbound, OpenAPI + AI Card outbound, media code resolution, and markdown normalization. | ✅ |
| helpers.py | Core | Pure helper functions for DingTalk channel (callback parsing, signature verification, media extraction from richText). | ✅ |
| models.py | Core | Pydantic models for DingTalk robot callback payloads (text, richText with media, picture, file). | ✅ |

## AI Card Streaming

When `card_template_id` is configured, outbound responses use DingTalk AI Cards
with streaming updates (typewriter effect). Without it, responses degrade
transparently to plain Markdown messages.

**API flow**: `createAndDeliver` → `streaming_update` (× N) → `streaming_update(is_finalize=True)`

## Media Handling

**Inbound**: DingTalk sends `downloadCode` tokens (not URLs) for media attachments.
`_resolve_media_codes` concurrently resolves these via the Robot Message File Download API
so downstream consumers (Vision LLM) can access media content. Supports picture messages,
file messages, and richText messages with embedded images.

**Outbound**: Three-level media fallback (URL direct → upload+send → file send → text fallback).

## Markdown Normalization

DingTalk's markdown renderer has platform-specific quirks. `_normalize_dingtalk_markdown`
ensures correct rendering by:
- Inserting blank lines before numbered list items
- Dedenting indented code fences to column 0
