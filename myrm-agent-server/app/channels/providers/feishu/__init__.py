"""Feishu/Lark channel provider — bidirectional messaging via Open API.

Exports:
- FeishuChannel: Main channel (webhook + websocket dual transport)
- FeishuClient: Standalone async API client (httpx-based)
- FeishuWSTransport: WebSocket transport via lark-oapi SDK
- FeishuAppRegistration: QR scan-to-create app registration (device-code flow)
- Card builders, parser, and streaming utilities
"""

from .api import FeishuClient
from .cards import (
    build_card_actions,
    build_component_card,
    build_post_content,
    build_result_card,
    build_thinking_card,
    has_rich_text,
    merge_streaming_text,
    parse_card_action,
    resolve_send_mode,
    wrap_text_as_card,
)
from .channel import FeishuChannel
from .parser import (
    FeishuInboundEvent,
    PostParseResult,
    extract_message_text,
    parse_inbound_event,
    parse_post_content,
)
from .registration import FeishuAppRegistration
from .webhook_utils import (
    extract_channel_user_id,
    extract_chat_id,
    is_url_verification_challenge,
    parse_webhook_headers,
    verify_webhook_signature,
)
from .ws_transport import FeishuWSTransport

__all__ = [
    "FeishuAppRegistration",
    "FeishuChannel",
    "FeishuClient",
    "FeishuInboundEvent",
    "FeishuWSTransport",
    "PostParseResult",
    "build_card_actions",
    "build_component_card",
    "build_post_content",
    "build_result_card",
    "build_thinking_card",
    "extract_channel_user_id",
    "extract_chat_id",
    "extract_message_text",
    "has_rich_text",
    "is_url_verification_challenge",
    "merge_streaming_text",
    "parse_card_action",
    "parse_inbound_event",
    "parse_post_content",
    "parse_webhook_headers",
    "resolve_send_mode",
    "verify_webhook_signature",
    "wrap_text_as_card",
]
