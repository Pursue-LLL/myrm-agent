"""[INPUT]
(none)

[OUTPUT]
- PRODUCT_MEDIA_TOOL_NAMES: frozenset of media tool names for registration checks

[POS]
Product media tool name SSOT (server business layer).
"""

from __future__ import annotations

PRODUCT_MEDIA_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "image_tool",
        "video_tool",
        "tts_generate",
    }
)
