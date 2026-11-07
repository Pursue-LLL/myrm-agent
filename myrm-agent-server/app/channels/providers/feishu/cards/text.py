"""[INPUT]
- （无跨模块依赖）

[OUTPUT]
- merge_streaming_text: Merge streaming text fragments with correct precedence.
- resolve_send_mode: Determine Feishu message send mode based on context.
- has_rich_text: Detect if content has rich formatting that benefits from post type.
- _parse_post_line: Parse a single line of Markdown into Feishu post elements.
- build_post_content: Convert Markdown-like text to Feishu post (rich text) format.

[POS]
飞书卡片子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    pass

SendMode = Literal["reply", "root_create", "create"]

_CARD_CONFIG: dict[str, object] = {"wide_screen_mode": True, "enable_forward": True}
_ACTION_VALUE_MAX = 200

_HEADER_TEMPLATES: dict[bool | None, tuple[str, str]] = {
    True: ("green", ""),
    False: ("red", ""),
    None: ("blue", ""),
}

_FEISHU_BUTTON_TYPE: dict[str, str] = {
    "primary": "primary",
    "danger": "danger",
    "default": "default",
}


# ── Component card (from OutboundMessage) ────────────────────────


def merge_streaming_text(previous: str, next_chunk: str) -> str:
    """Merge streaming text fragments with correct precedence.

    Priority: full containment > partial overlap > fallback append.
    """
    if not previous:
        return next_chunk
    if not next_chunk:
        return previous

    if next_chunk.startswith(previous):
        return next_chunk
    if previous.startswith(next_chunk):
        return previous
    if next_chunk in previous:
        return previous
    if previous in next_chunk:
        return next_chunk

    max_overlap = min(len(previous), len(next_chunk))
    for overlap in range(max_overlap, 0, -1):
        if previous.endswith(next_chunk[:overlap]):
            return f"{previous}{next_chunk[overlap:]}"

    return f"{previous}{next_chunk}"


# ── Send mode resolution ─────────────────────────────────────────


def resolve_send_mode(
    *,
    reply_to_id: str | None = None,
    root_id: str | None = None,
) -> SendMode:
    """Determine Feishu message send mode based on context.

    Priority: reply > root_create > create.
    """
    if reply_to_id:
        return "reply"
    if root_id:
        return "root_create"
    return "create"


# ── Post (rich text) format builders ─────────────────────────────

_RICH_TEXT_RE = re.compile(
    r"\*\*.+?\*\*" r"|(?<!\w)_.+?_(?!\w)" r"|\[.+?\]\(.+?\)" r"|~~.+?~~" r"|`[^`]+`",
)
_HEADING_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_POST_INLINE_RE = re.compile(
    r"(\*\*(.+?)\*\*)" r"|(~~(.+?)~~)" r"|(`([^`]+)`)" r"|(\[(.+?)\]\((.+?)\))",
)


def has_rich_text(content: str) -> bool:
    """Detect if content has rich formatting that benefits from post type."""
    return bool(_RICH_TEXT_RE.search(content) or _HEADING_RE.search(content))


def _parse_post_line(line: str) -> list[dict[str, object]]:
    """Parse a single line of Markdown into Feishu post elements."""
    elements: list[dict[str, object]] = []
    pos = 0
    for m in _POST_INLINE_RE.finditer(line):
        if m.start() > pos:
            elements.append({"tag": "text", "text": line[pos : m.start()]})
        if m.group(2) is not None:
            elements.append({"tag": "text", "text": m.group(2), "style": ["bold"]})
        elif m.group(4) is not None:
            elements.append({"tag": "text", "text": m.group(4), "style": ["lineThrough"]})
        elif m.group(6) is not None:
            elements.append({"tag": "text", "text": m.group(6), "style": ["code"]})
        elif m.group(8) is not None:
            elements.append({"tag": "a", "text": m.group(8), "href": m.group(9)})
        pos = m.end()
    if pos < len(line):
        elements.append({"tag": "text", "text": line[pos:]})
    return elements or [{"tag": "text", "text": line}]


def build_post_content(content: str) -> dict[str, object]:
    """Convert Markdown-like text to Feishu post (rich text) format.

    Produces a post payload with zh_cn locale. Handles bold, italic,
    inline code, links, and headings by mapping to Feishu post tags.
    """
    paragraphs: list[list[dict[str, object]]] = []
    for line in content.split("\n"):
        elements: list[dict[str, object]] = []
        heading_match = _HEADING_RE.match(line)
        if heading_match:
            line = line[heading_match.end() :]
            elements.append({"tag": "text", "text": line, "style": ["bold"]})
        else:
            elements.extend(_parse_post_line(line))
        paragraphs.append(elements)
    return {"zh_cn": {"title": "", "content": paragraphs}}


# ── Contact Disambiguation and Deliverable Cards ─────────────────
