"""WhatsApp format converter — Markdown to WhatsApp syntax.

Converts standard Markdown to WhatsApp-supported formatting:
- **bold** / __bold__ → *bold*
- ~~strikethrough~~ → ~strikethrough~
- Preserves code fences (```...```) and inline code (`...`)

[INPUT]

[OUTPUT]
- WhatsApp-formatted text

[POS]
WhatsApp format conversion. Protects code blocks/inline code, converts
formatting markers, restores protected content.
"""

from __future__ import annotations

import re

_FENCE_PLACEHOLDER = "\x00FENCE"
_INLINE_CODE_PLACEHOLDER = "\x00CODE"

_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```")
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_BOLD_DOUBLE_STAR_RE = re.compile(r"\*\*(.+?)\*\*")
_BOLD_DOUBLE_UNDERSCORE_RE = re.compile(r"__(.+?)__")
_STRIKE_RE = re.compile(r"~~(.+?)~~")
_HEADER_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def md_to_whatsapp(text: str) -> str:
    """Convert standard Markdown to WhatsApp format.

    Conversion rules:
    - **bold** → *bold*
    - __bold__ → *bold*
    - ~~strikethrough~~ → ~strikethrough~
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
        return f"{_FENCE_PLACEHOLDER}{len(fences) - 1}"

    result = _CODE_FENCE_RE.sub(save_fence, text)

    # Step 2: Extract and protect inline code
    inline_codes: list[str] = []

    def save_inline_code(match: re.Match[str]) -> str:
        inline_codes.append(match.group(0))
        return f"{_INLINE_CODE_PLACEHOLDER}{len(inline_codes) - 1}"

    result = _INLINE_CODE_RE.sub(save_inline_code, result)

    # Step 3: Convert formatting markers
    result = _BOLD_DOUBLE_STAR_RE.sub(r"*\1*", result)
    result = _BOLD_DOUBLE_UNDERSCORE_RE.sub(r"*\1*", result)
    result = _STRIKE_RE.sub(r"~\1~", result)

    # Step 3b: Convert headers to bold and links to readable format
    def _header_to_bold(m: re.Match[str]) -> str:
        inner = m.group(1).strip()
        while len(inner) > 1 and inner.startswith("*") and inner.endswith("*"):
            inner = inner[1:-1].strip()
        return f"*{inner}*"

    result = _HEADER_RE.sub(_header_to_bold, result)
    result = _LINK_RE.sub(r"\1 (\2)", result)

    # Step 4: Restore inline code
    def restore_inline_code(match: re.Match[str]) -> str:
        idx = int(match.group(1))
        return inline_codes[idx] if idx < len(inline_codes) else ""

    result = re.sub(
        rf"{re.escape(_INLINE_CODE_PLACEHOLDER)}(\d+)",
        restore_inline_code,
        result,
    )

    # Step 5: Restore code fences
    def restore_fence(match: re.Match[str]) -> str:
        idx = int(match.group(1))
        return fences[idx] if idx < len(fences) else ""

    result = re.sub(
        rf"{re.escape(_FENCE_PLACEHOLDER)}(\d+)",
        restore_fence,
        result,
    )

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
