# feishu/

## Overview
Feishu/Lark channel provider — bidirectional messaging and document comment interaction via Open API.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Feishu/Lark channel provider — bidirectional messaging via Open API. | — |
| api.py | Re-export | Re-exports FeishuClient and exceptions from local sdk/ package. | ✅ |
| cards.py | Core | Feishu card builders, post format builders, and streaming text utilities. | ✅ |
| channel.py | Core | Feishu/Lark channel — dual transport (webhook / websocket) bidirectional messaging. Handles im.message.receive_v1, card.action.trigger, im.message.reaction_created_v1, drive.notice.comment_add_v1 events. | ✅ |
| comment_content.py | Core | Comment content extraction and prompt construction. Pure functions for text parsing, timeline selection, doc link resolution, and prompt building. | ✅ |
| comment_handler.py | Core | Drive document comment handler. Event orchestration, routing (encode/parse chat_id), and reply delivery with chunking. | ✅ |
| models.py | Core | Pydantic models for Feishu/Lark event subscription webhook payloads. | ✅ |
| parser.py | Core | Feishu inbound message parser. Converts Feishu event JSON to structured data. | ✅ |
| webhook_utils.py | Core | Feishu Webhook utility functions for signature verification and metadata extraction. | ✅ |
| registration.py | Core | Feishu device-code flow for automated app creation via QR scan. | ✅ |
| ws_transport.py | Core | Feishu WebSocket transport layer. Wraps lark-oapi SDK WS client. Missing SDK: `uv sync` (main dep). | ✅ |

| Submodule | Description |
|-----------|-------------|
| sdk/ | Feishu/Lark OpenAPI SDK — standalone HTTP client (Mixin-based). Token management, messaging, media, documents, CardKit, Bitable, Docx. |

## QR Code App Registration

The `registration.py` module implements the Feishu device-code flow for automated app creation:

1. `begin()` → initiates device-code registration, returns QR URL + device_code
2. Frontend renders QR code from URL, user scans with Feishu app
3. `poll(device_code)` → polls registration status (pending/success/denied/expired)
4. On success → returns `app_id`, `app_secret`, `bot_open_id` credentials
5. `probe_bot(app_id, app_secret)` → verifies the created bot is functional

The server layer (`feishu_register.py`) exposes REST endpoints that bridge this flow
to the frontend and saves credentials to the UserConfig DB (not CredentialsStore).

## Document Comment System

The comment system uses a **chat_id encoding** strategy to route document comments
through the existing agent pipeline with zero intrusion:

1. `drive.notice.comment_add_v1` → `CommentHandler` parses and builds prompt
2. `InboundMessage.chat_id` = `comment-doc:{file_type}:{file_token}:{comment_id}:{is_whole}`
3. Agent processes normally via `_emit_inbound` pipeline
4. `OutboundMessage.recipient_id` carries the encoded chat_id
5. `FeishuChannel.send()` detects `comment-doc:` prefix → comment reply API
