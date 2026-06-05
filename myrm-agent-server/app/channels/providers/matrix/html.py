"""Markdown → Matrix HTML conversion utilities.

[INPUT]
- channels.rendering.text_utils::extract_safe_regions (POS: Universal text utilities)

[OUTPUT]
- md_to_matrix_html: Markdown → HTML subset (or None for plain text)
- build_text_payload: Matrix m.text payload with optional formatted_body
- convert_matrix_mentions: Convert @user to @user:server.com (code-block-aware)
- strip_matrix_mention: Strip bot's own Matrix mention from text

[POS]
Lightweight regex-based Markdown→HTML converter for Matrix ``org.matrix.custom.html``.
Supports: code blocks, inline code, bold, italic, strikethrough, links, headings,
unordered/ordered lists, blockquotes, mentions (@user → qualified Matrix ID).
Zero external dependencies for HTML conversion; uses text_utils for code block protection.
"""

from __future__ import annotations

import html
import re

from app.channels.rendering.text_utils import extract_safe_regions

_CODE_BLOCK_RE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_STRIKE_RE = re.compile(r"~~(.+?)~~")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_UL_LINE_RE = re.compile(r"^[-*]\s+(.+)$")
_OL_LINE_RE = re.compile(r"^\d+\.\s+(.+)$")
_QUOTE_LINE_RE = re.compile(r"^&gt;\s?(.*)$")
MATRIX_HTML_FORMAT = "org.matrix.custom.html"


def _convert_block_structures(lines: list[str]) -> list[str]:
    """Convert consecutive list / blockquote lines into HTML block elements."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        ul = _UL_LINE_RE.match(lines[i])
        if ul:
            items: list[str] = []
            while i < len(lines) and (m := _UL_LINE_RE.match(lines[i])):
                items.append(f"<li>{m.group(1)}</li>")
                i += 1
            out.append(f"<ul>{''.join(items)}</ul>")
            continue

        ol = _OL_LINE_RE.match(lines[i])
        if ol:
            items = []
            while i < len(lines) and (m := _OL_LINE_RE.match(lines[i])):
                items.append(f"<li>{m.group(1)}</li>")
                i += 1
            out.append(f"<ol>{''.join(items)}</ol>")
            continue

        qm = _QUOTE_LINE_RE.match(lines[i])
        if qm:
            parts: list[str] = []
            while i < len(lines) and (m := _QUOTE_LINE_RE.match(lines[i])):
                parts.append(m.group(1))
                i += 1
            out.append(f"<blockquote>{' '.join(parts)}</blockquote>")
            continue

        out.append(lines[i])
        i += 1
    return out


def md_to_matrix_html(text: str) -> str | None:
    """Convert Markdown to Matrix-compatible HTML subset.

    Returns None if the result is plain text with no formatting
    (avoids unnecessary ``formatted_body`` overhead).
    """
    preserved: list[str] = []

    def _preserve_block(m: re.Match[str]) -> str:
        lang, code = m.group(1), m.group(2)
        tag = (
            f'<pre><code class="language-{lang}">{html.escape(code)}</code></pre>' if lang else f"<pre>{html.escape(code)}</pre>"
        )
        preserved.append(tag)
        return f"\x00P{len(preserved) - 1}\x00"

    def _preserve_inline(m: re.Match[str]) -> str:
        tag = f"<code>{html.escape(m.group(1))}</code>"
        preserved.append(tag)
        return f"\x00P{len(preserved) - 1}\x00"

    result = _CODE_BLOCK_RE.sub(_preserve_block, text)
    result = _INLINE_CODE_RE.sub(_preserve_inline, result)
    result = html.escape(result)
    result = _BOLD_RE.sub(r"<strong>\1</strong>", result)
    result = _ITALIC_RE.sub(r"<em>\1</em>", result)
    result = _STRIKE_RE.sub(r"<del>\1</del>", result)
    result = _LINK_RE.sub(r'<a href="\2">\1</a>', result)
    result = _HEADING_RE.sub(
        lambda m: f"<h{len(m.group(1))}>{m.group(2)}</h{len(m.group(1))}>",
        result,
    )

    lines = result.split("\n")
    lines = _convert_block_structures(lines)
    result = "\n".join(lines)

    for idx, tag in enumerate(preserved):
        result = result.replace(f"\x00P{idx}\x00", tag)

    if "<" not in result:
        return None
    return result


def build_text_payload(text: str) -> dict[str, object]:
    """Build Matrix m.text payload with optional HTML formatting."""
    payload: dict[str, object] = {"msgtype": "m.text", "body": text}
    if formatted := md_to_matrix_html(text):
        payload["format"] = MATRIX_HTML_FORMAT
        payload["formatted_body"] = formatted
    return payload


_MENTION_RE = re.compile(r"@(\w+)")
_QUALIFIED_MENTION_RE = re.compile(r"@[\w.-]+:[\w.-]+(?::\d+)?")  # @user:server.com or @user:server.com:8448


def strip_matrix_mention(text: str, bot_user_id: str) -> str:
    """Strip bot's own Matrix mention from text.

    Args:
        text: Input text with potential bot mention
        bot_user_id: Bot's qualified Matrix ID (e.g., @bot:matrix.org)

    Returns:
        Text with bot mention removed (leading/trailing whitespace stripped)

    Example:
        >>> strip_matrix_mention("@bot:matrix.org hello", "@bot:matrix.org")
        "hello"
    """
    if not text or not bot_user_id:
        return text.strip()

    escaped_bot_id = re.escape(bot_user_id)
    pattern = rf"^{escaped_bot_id}\s*"
    return re.sub(pattern, "", text).strip()


def convert_matrix_mentions(
    text: str,
    room_members: dict[str, str],
) -> str:
    """Convert @user mentions to qualified Matrix IDs (@user:server.com).

    Uses code-block-aware extraction to avoid processing mentions
    inside code blocks (e.g., @alice in ```code``` is preserved).

    Args:
        text: Input text with @mentions
        room_members: Mapping of displayname -> qualified Matrix ID
                      Example: {"alice": "@alice:matrix.org", "bob": "@bob:server.com"}

    Returns:
        Text with @user converted to @user:server.com (outside code blocks only)

    Example:
        >>> members = {"alice": "@alice:matrix.org"}
        >>> text = "Hi @alice, check ```@bob in code```"
        >>> convert_matrix_mentions(text, members)
        "Hi @alice:matrix.org, check ```@bob in code```"
    """
    matches = extract_safe_regions(text, _MENTION_RE)
    if not matches:
        return text

    replacements: list[tuple[int, int, str]] = []

    for match in matches:
        username = match.group(1)
        qualified_id = room_members.get(username)
        if qualified_id:
            replacements.append((match.start(), match.end(), qualified_id))

    if not replacements:
        return text

    replacements.sort(reverse=True)

    result = text
    for start, end, replacement in replacements:
        result = result[:start] + replacement + result[end:]

    return result
