"""Slack format converter — Markdown to Slack mrkdwn format.

Handles special character escaping, Slack token protection, link conversion,
and CJK formatting boundary insertion.

[INPUT]

[OUTPUT]
- str: Slack mrkdwn-formatted text

[POS]
Markdown → Slack mrkdwn converter. Escapes special chars (&, <, >),
protects Slack angle-bracket tokens (<@mention>, <#channel>, <http://...>),
converts Markdown links to Slack format, handles bold/strike formatting,
and inserts zero-width spaces at CJK formatting boundaries.
"""

from __future__ import annotations

import re

_SLACK_ANGLE_TOKEN_RE = re.compile(r"<[^>\n]+>")
_CODE_FENCE_RE = re.compile(r"^```")  # Match code fence start/end
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"\*(?!\*)([^*]+?)\*(?!\*)")  # *italic* (not **bold**)
_STRIKE_RE = re.compile(r"~~(.+?)~~")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

# CJK / Hangul character range for word-boundary insertion.
# Slack mrkdwn formatting chars (*, _, ~) need word boundaries to render;
# CJK/Hangul characters are not word boundaries, so we insert U+200B
# (zero-width space) between these chars and formatting markers.
# Ranges: CJK radicals+unified+kana (2E80-9FFF), Hangul syllables (AC00-D7AF),
#          CJK compat ideographs (F900-FAFF), CJK compat forms (FE30-FE4F),
#          fullwidth forms (FF00-FFEF).
_CJK_CHAR = re.compile(r"[\u2E80-\u9FFF\uAC00-\uD7AF\uF900-\uFAFF\uFE30-\uFE4F\uFF00-\uFFEF]")
_ZWS = "\u200b"


def _is_allowed_slack_token(token: str) -> bool:
    """Check if an angle-bracket token should be preserved (not escaped).

    Allowed tokens:
    - <@USER_ID>: User mentions
    - <#CHANNEL_ID>: Channel references
    - <!here>, <!channel>, <!everyone>: Special mentions
    - <http://...>, <https://...>: Links
    - <mailto:...>, <tel:...>: Protocol links
    - <slack://...>: Slack deep links

    Args:
        token: Full token including angle brackets (e.g., "<@U123456>")

    Returns:
        True if token should be preserved, False if it should be escaped
    """
    if not token.startswith("<") or not token.endswith(">"):
        return False

    inner = token[1:-1]
    return (
        inner.startswith("@")
        or inner.startswith("#")
        or inner.startswith("!")
        or inner.startswith("mailto:")
        or inner.startswith("tel:")
        or inner.startswith("http://")
        or inner.startswith("https://")
        or inner.startswith("slack://")
    )


def _escape_slack_segment(text: str) -> str:
    """Escape special characters for Slack mrkdwn format.

    Escapes: & → &amp;, < → &lt;, > → &gt;
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_slack_content(text: str) -> str:
    """Escape special chars while preserving allowed Slack angle-bracket tokens.

    Strategy:
    1. Find all <...> tokens using regex
    2. For each token:
       - If allowed (mention/channel/link) → preserve
       - If not allowed → escape
    3. Escape all content between tokens

    Args:
        text: Input text (may contain Slack tokens and special chars)

    Returns:
        Text with special chars escaped, allowed tokens preserved
    """
    if not text:
        return ""

    if "&" not in text and "<" not in text and ">" not in text:
        return text

    parts: list[str] = []
    last_end = 0

    for match in _SLACK_ANGLE_TOKEN_RE.finditer(text):
        parts.append(_escape_slack_segment(text[last_end : match.start()]))

        token = match.group(0)
        if _is_allowed_slack_token(token):
            parts.append(token)
        else:
            parts.append(_escape_slack_segment(token))

        last_end = match.end()

    parts.append(_escape_slack_segment(text[last_end:]))
    return "".join(parts)


def _escape_slack_content_fence_aware(text: str) -> str:
    """Escape content while preserving code fence internals.

    Code fences (```...```) should not have their content escaped.
    This prevents `<div>` from becoming `&lt;div&gt;` inside code blocks.

    Strategy:
    1. Split text into lines
    2. Track fence state (in_fence vs outside)
    3. Escape only lines outside code fences
    4. Preserve fence lines and content inside fences as-is

    Args:
        text: Input text (may contain code fences and special chars)

    Returns:
        Text with special chars escaped outside fences, fences preserved
    """
    if not text:
        return ""

    lines = text.split("\n")
    result_lines: list[str] = []
    in_fence = False

    for line in lines:
        stripped = line.strip()

        # Check if this line is a fence delimiter
        if _CODE_FENCE_RE.match(stripped):
            in_fence = not in_fence
            result_lines.append(line)  # Fence line itself, no escape
        elif in_fence:
            result_lines.append(line)  # Inside fence, no escape
        else:
            result_lines.append(_escape_slack_content(line))  # Outside fence, escape

    return "\n".join(result_lines)


def _fix_cjk_formatting_boundaries(text: str) -> str:
    """Insert zero-width spaces between CJK chars and Slack formatting markers.

    Slack requires word boundaries around *, _, ~ to render formatting.
    CJK characters are not word boundaries, so `中文*加粗*text` won't render
    bold. Inserting U+200B forces the boundary without visible side effects.
    """
    if not text:
        return text

    result: list[str] = []
    length = len(text)

    for i, ch in enumerate(text):
        if ch in ("*", "_", "~"):
            if result and _CJK_CHAR.match(result[-1]):
                result.append(_ZWS)
            result.append(ch)
            if i + 1 < length and _CJK_CHAR.match(text[i + 1]):
                result.append(_ZWS)
        else:
            result.append(ch)

    return "".join(result)


def _convert_markdown_link(match: re.Match[str]) -> str:
    """Convert Markdown link to Slack link format.

    Markdown: [text](url)
    Slack: <url|text>

    Only converts if text != url (to avoid redundant <url|url> format).
    """
    text = match.group(1).strip()
    url = match.group(2).strip()

    if not url:
        return match.group(0)

    comparable_url = url[len("mailto:") :] if url.startswith("mailto:") else url

    if text and text != url and text != comparable_url:
        safe_url = _escape_slack_segment(url)
        return f"<{safe_url}|{text}>"

    return match.group(0)


def md_to_slack_mrkdwn(text: str) -> str:
    """Convert Markdown to Slack mrkdwn format.

    Transformations:
    1. **bold** → *bold* (outside code fences only)
    2. *italic* → _italic_ (outside code fences only)
    3. ~~strike~~ → ~strike~ (outside code fences only)
    4. [text](url) → <url|text> (outside code fences only, only if text != url)
    5. Escape special chars (&, <, >) while preserving Slack tokens and code fences
    6. Insert zero-width spaces at CJK formatting boundaries

    Args:
        text: Markdown-formatted text

    Returns:
        Slack mrkdwn-formatted text

    Example:
        >>> md_to_slack_mrkdwn("**Hello** *world* <@U123> [link](http://example.com)")
        '*Hello* _world_ <@U123> <http://example.com|link>'
    """
    if not text:
        return ""

    # Strategy: Process line-by-line to respect code fence boundaries
    lines = text.split("\n")
    result_lines: list[str] = []
    in_fence = False

    for line in lines:
        stripped = line.strip()

        # Check if this line is a fence delimiter
        if _CODE_FENCE_RE.match(stripped):
            in_fence = not in_fence
            result_lines.append(line)  # Fence line, no transformation
            continue

        if in_fence:
            # Inside fence: no transformations, no escape
            result_lines.append(line)
        else:
            # Outside fence: apply all transformations
            # 1. Bold (with temporary marker)
            result = _BOLD_RE.sub(r"⟪BOLD⟫\1⟪/BOLD⟫", line)
            # 2. Italic
            result = _ITALIC_RE.sub(r"_\1_", result)
            # 3. Replace bold markers
            result = result.replace("⟪BOLD⟫", "*").replace("⟪/BOLD⟫", "*")
            # 4. Strike
            result = _STRIKE_RE.sub(r"~\1~", result)
            # 5. Links
            result = _MARKDOWN_LINK_RE.sub(_convert_markdown_link, result)
            # 6. Escape
            result = _escape_slack_content(result)
            # 7. CJK boundary fix
            result = _fix_cjk_formatting_boundaries(result)
            result_lines.append(result)

    return "\n".join(result_lines)
