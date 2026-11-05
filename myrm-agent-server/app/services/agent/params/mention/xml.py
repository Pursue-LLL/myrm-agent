"""[INPUT]
- xml.sax.saxutils::escape / quoteattr (POS: XML attribute and body escaping)

[OUTPUT]
- _xml_part / _xml_metadata / _xml_error: the three `<mentioned_file>` fragment shapes
- _format_size / _can_inline: the inline budget every reference handler shares
- _MENTION_MAX_INLINE_BYTES / _MENTION_MAX_TOTAL_BYTES

[POS]
Presentation primitives of the @-mention subsystem. Every handler emits one of these fragments, so
the prompt format and the byte budget have exactly one definition.
"""

from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr

_MENTION_MAX_INLINE_BYTES = 100 * 1024  # 100KB per file
_MENTION_MAX_TOTAL_BYTES = 500 * 1024  # 500KB total


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes}B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    return f"{size_bytes / (1024 * 1024):.1f}MB"


def _can_inline(content_bytes: int, current_total_bytes: int) -> bool:
    return content_bytes <= _MENTION_MAX_INLINE_BYTES and current_total_bytes + content_bytes <= _MENTION_MAX_TOTAL_BYTES


def _xml_part(path: str, part_type: str, content: str) -> str:
    return f"<mentioned_file path={quoteattr(path)} type={quoteattr(part_type)}>\n{escape(content)}\n</mentioned_file>"


def _xml_metadata(path: str, part_type: str, message: str) -> str:
    return f"<mentioned_file path={quoteattr(path)} type={quoteattr(part_type)}>{escape(message)}</mentioned_file>"


def _xml_error(path: str, message: str) -> str:
    return f"<mentioned_file path={quoteattr(path)} error={quoteattr(message)}/>"
