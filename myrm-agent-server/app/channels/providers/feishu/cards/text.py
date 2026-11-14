"""[INPUT]
- （无跨模块依赖）

[OUTPUT]
- resolve_send_mode: Determine Feishu message send mode based on context.
- has_rich_text: Detect if content has rich formatting that benefits from post type.
- _parse_post_line: Parse a single line of Markdown into Feishu post elements.
- _bolded: Add the bold style to a post element.
- build_post_content: Convert Markdown-like text to Feishu post (rich text) format.

[POS]
飞书卡片子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import re
from typing import Literal

SendMode = Literal["reply", "root_create", "create"]


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
            # A post text element has no code style (Feishu ignores unknown styles), so the backticks stay as the cue.
            elements.append({"tag": "text", "text": m.group(0)})
        elif m.group(8) is not None:
            elements.append({"tag": "a", "text": m.group(8), "href": m.group(9)})
        pos = m.end()
    if pos < len(line):
        elements.append({"tag": "text", "text": line[pos:]})
    return elements or [{"tag": "text", "text": line}]


def _bolded(element: dict[str, object]) -> dict[str, object]:
    """``element`` with the bold style added to the styles it has."""
    styles = element.get("style")
    existing = [str(style) for style in styles] if isinstance(styles, list) else []
    return {**element, "style": list(dict.fromkeys(["bold", *existing]))}


def build_post_content(content: str) -> dict[str, object]:
    """Convert Markdown-like text to Feishu post (rich text) format.

    Produces a post payload with zh_cn locale. Handles bold, strikethrough, inline code,
    links and headings (bold, with their own inline spans) by mapping to Feishu post tags.
    """
    paragraphs: list[list[dict[str, object]]] = []
    for line in content.split("\n"):
        heading_match = _HEADING_RE.match(line)
        if heading_match:
            paragraphs.append([_bolded(element) for element in _parse_post_line(line[heading_match.end() :])])
        else:
            paragraphs.append(_parse_post_line(line))
    return {"zh_cn": {"title": "", "content": paragraphs}}
