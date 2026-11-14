"""WhatsApp format converter — Markdown to WhatsApp syntax.

Converts standard Markdown to WhatsApp-supported formatting:
- **bold** / __bold__ → *bold*
- ~~strikethrough~~ → ~strikethrough~
- # heading → *heading* (a bold line; the bold marks inside it are dropped, WhatsApp cannot nest bold)
- Preserves code fences (```...```) and inline code (`...`)

[INPUT]
- none (imports no other project module)

[OUTPUT]
- WhatsApp-formatted text

[POS]
WhatsApp format conversion. Protects code blocks/inline code, converts
formatting markers, restores protected content.
"""

from __future__ import annotations

import re

# Closed by NUL like the other converters: an index never swallows the digit that follows the code.
_FENCE_PLACEHOLDER = "\x00FENCE{}\x00"
_INLINE_CODE_PLACEHOLDER = "\x00CODE{}\x00"
_FENCE_PLACEHOLDER_RE = re.compile(r"\x00FENCE(\d+)\x00")
_INLINE_CODE_PLACEHOLDER_RE = re.compile(r"\x00CODE(\d+)\x00")

# From a run of three to ten backticks to the next run of the same length: a block fenced by four keeps whole the
# blocks it documents.
_CODE_FENCE_RE = re.compile(r"(?P<fence>`{3,10})[\s\S]*?(?P=fence)")
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_BOLD_DOUBLE_STAR_RE = re.compile(r"\*\*(.+?)\*\*")
_BOLD_DOUBLE_UNDERSCORE_RE = re.compile(r"__(.+?)__")
_STRIKE_RE = re.compile(r"~~(.+?)~~")
# Spaces or tabs only: a lone "#" on a line must not take the next line (or the blank lines before it) as its text.
_HEADER_RE = re.compile(r"^#{1,6}[ \t]+(.+)$", re.MULTILINE)
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def md_to_whatsapp(text: str) -> str:
    """Convert standard Markdown to WhatsApp format.

    Conversion rules:
    - **bold** → *bold*
    - __bold__ → *bold*
    - ~~strikethrough~~ → ~strikethrough~
    - # heading → *heading*, without the bold marks inside it
    - Code fences and inline code are preserved unchanged

    Args:
        text: Standard Markdown text

    Returns:
        WhatsApp-formatted text

    Example:
        >>> md_to_whatsapp("**bold** and ~~strike~~ text")
        "*bold* and ~strike~ text"
        >>> md_to_whatsapp("Code: `print('hello')`")
        "Code: `print('hello')`"
    """
    if not text:
        return text

    # Step 1: Extract and protect code fences
    fences: list[str] = []

    def save_fence(match: re.Match[str]) -> str:
        fences.append(match.group(0))
        return _FENCE_PLACEHOLDER.format(len(fences) - 1)

    result = _CODE_FENCE_RE.sub(save_fence, text)

    # Step 2: Extract and protect inline code
    inline_codes: list[str] = []

    def save_inline_code(match: re.Match[str]) -> str:
        inline_codes.append(match.group(0))
        return _INLINE_CODE_PLACEHOLDER.format(len(inline_codes) - 1)

    result = _INLINE_CODE_RE.sub(save_inline_code, result)

    # Step 3: Convert headers to one bold line. WhatsApp cannot nest bold in bold, so the bold markers inside a header
    # go before the line is wrapped ("## **Quick Start** guide" is "*Quick Start guide*", not "**Quick Start* guide*")
    def _header_to_bold(m: re.Match[str]) -> str:
        inner = _BOLD_DOUBLE_STAR_RE.sub(r"\1", m.group(1))
        inner = _BOLD_DOUBLE_UNDERSCORE_RE.sub(r"\1", inner)
        return f"*{inner.strip()}*"

    result = _HEADER_RE.sub(_header_to_bold, result)

    # Step 3b: Convert formatting markers and links to readable format
    result = _BOLD_DOUBLE_STAR_RE.sub(r"*\1*", result)
    result = _BOLD_DOUBLE_UNDERSCORE_RE.sub(r"*\1*", result)
    result = _STRIKE_RE.sub(r"~\1~", result)
    result = _LINK_RE.sub(r"\1 (\2)", result)

    # Step 4: Restore inline code
    def restore_inline_code(match: re.Match[str]) -> str:
        idx = int(match.group(1))
        return inline_codes[idx] if idx < len(inline_codes) else ""

    result = _INLINE_CODE_PLACEHOLDER_RE.sub(restore_inline_code, result)

    # Step 5: Restore code fences
    def restore_fence(match: re.Match[str]) -> str:
        idx = int(match.group(1))
        return fences[idx] if idx < len(fences) else ""

    result = _FENCE_PLACEHOLDER_RE.sub(restore_fence, result)

    return result


def validate_whatsapp_format(text: str) -> tuple[bool, str]:
    """Validate WhatsApp format constraints.

    WhatsApp limitations:
    - No nested formatting (e.g., *_bold italic_* not supported)
    - Maximum 4KB message size

    Args:
        text: WhatsApp-formatted text

    Returns:
        (is_valid, error_message) tuple

    Example:
        >>> validate_whatsapp_format("*bold*")
        (True, "")
        >>> validate_whatsapp_format("*_nested_*")
        (False, "Nested formatting not supported by WhatsApp")
    """
    if not text:
        return (True, "")

    # Check message size (WhatsApp limit: 4KB)
    if len(text.encode("utf-8")) > 4096:
        return (False, "Message exceeds WhatsApp 4KB limit")

    # Check for nested formatting patterns
    nested_patterns = [
        r"\*[^*]*_[^_]*_[^*]*\*",  # *..._..._...*
        r"_[^_]*\*[^*]*\*[^_]*_",  # _...*...*..._
        r"~[^~]*\*[^*]*\*[^~]*~",  # ~...*...*...~
    ]

    for pattern in nested_patterns:
        if re.search(pattern, text):
            return (False, "Nested formatting not supported by WhatsApp")

    return (True, "")
