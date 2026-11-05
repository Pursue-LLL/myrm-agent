"""Chat helper functions used by the agent pipeline.

[INPUT]
- myrm_agent_harness.utils.chat_utils / image_utils / json_parsing (POS: framework primitives)

[OUTPUT]
- Public chat helpers (history conversion, judge parsing, text extraction) and the image/video
  preprocessing helpers the streaming path and the tests use.

[POS]
Aggregate exit of the chat-utils package: history conversion, image compression, inbound multimodal
preprocessing and per-item image/video conversion each live in their own module.
"""

from __future__ import annotations

from myrm_agent_harness.utils.chat_utils import (
    ChatHistory,
    ChatHistoryReq,
    ContentItem,
    extract_answer_text,
    extract_litellm_answer_text,
)

from .history import convert_chat_history, parse_judge_json
from .image_items import _process_image_item
from .images import _compress_base64_image, _degrade_old_images, _needs_compression_base64
from .multimodal import _process_human_content, preprocess_inbound_multimodal_query
from .video_items import _process_video_item

__all__ = [
    "_process_human_content",
    "_process_image_item",
    "_process_video_item",
    "preprocess_inbound_multimodal_query",
    "_degrade_old_images",
    "_needs_compression_base64",
    "_compress_base64_image",
    "ChatHistory",
    "ChatHistoryReq",
    "ContentItem",
    "convert_chat_history",
    "extract_answer_text",
    "extract_litellm_answer_text",
    "parse_judge_json",
]
