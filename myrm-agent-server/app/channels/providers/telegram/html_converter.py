"""Markdown → Telegram HTML conversion.

Telegram HTML supports: <b>, <i>, <s>, <code>, <pre>, <a href>.
Only &, <, > need escaping in non-tag text — much simpler than MarkdownV2.

[INPUT]

[OUTPUT]
- md_to_telegram_html(): Telegram-safe HTML string
- split_message(): HTML-Aware UTF-16 safe splitting algorithm

[POS]
Markdown to Telegram HTML converter. Handles bold/italic/strikethrough/code/link,
supports 4096-char message splitting with state-machine-based HTML tag auto-closing
and UTF-16 surrogate pair protection.
"""

from __future__ import annotations

import html
import re

_MAX_MSG_LENGTH = 4096

_CODE_BLOCK_RE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_STRIKE_RE = re.compile(r"~~(.+?)~~")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

# Exact whitelist of Telegram supported HTML tags
_TELEGRAM_TAGS_RE = re.compile(
    r"(</?(?:b|strong|i|em|u|ins|s|strike|del|span|tg-spoiler|a|code|pre|blockquote|expandable)(?:\s+[^>]*)?>)",
    re.IGNORECASE,
)


def md_to_telegram_html(text: str) -> str:
    """Convert standard Markdown to Telegram-supported HTML subset.

    Preserves code blocks and inline code from further processing,
    then escapes HTML entities and applies formatting conversions.
    """
    preserved: list[str] = []

    def _preserve_code_block(m: re.Match[str]) -> str:
        lang, code = m.group(1), m.group(2)
        tag = (
            f'<pre><code class="language-{lang}">{html.escape(code)}</code></pre>'
            if lang
            else f"<pre>{html.escape(code)}</pre>"
        )
        preserved.append(tag)
        return f"\x00PRESERVE{len(preserved) - 1}\x00"

    def _preserve_inline_code(m: re.Match[str]) -> str:
        preserved.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00PRESERVE{len(preserved) - 1}\x00"

    result = _CODE_BLOCK_RE.sub(_preserve_code_block, text)
    result = _INLINE_CODE_RE.sub(_preserve_inline_code, result)

    # Split by PRESERVE placeholders AND Telegram-supported HTML tags to protect both
    _SPLIT_RE = re.compile(r"(\x00PRESERVE\d+\x00)|" + _TELEGRAM_TAGS_RE.pattern)
    parts = _SPLIT_RE.split(result)
    escaped_parts: list[str] = []
    for part in parts:
        if part is None:
            continue
        if (part.startswith("\x00PRESERVE") and part.endswith("\x00")) or _TELEGRAM_TAGS_RE.fullmatch(part):
            escaped_parts.append(part)
        else:
            escaped_parts.append(html.escape(part))
    result = "".join(escaped_parts)

    result = _BOLD_RE.sub(r"<b>\1</b>", result)
    result = _ITALIC_RE.sub(r"<i>\1</i>", result)
    result = _STRIKE_RE.sub(r"<s>\1</s>", result)
    result = _LINK_RE.sub(r'<a href="\2">\1</a>', result)

    for i, block in enumerate(preserved):
        result = result.replace(f"\x00PRESERVE{i}\x00", block)

    return result


def _utf16_len(s: str) -> int:
    """Calculate the length of a string in UTF-16 code units."""
    return len(s.encode("utf-16-le")) // 2


def split_message(text: str, limit: int = _MAX_MSG_LENGTH) -> list[str]:
    """HTML-Aware UTF-16 safe splitting algorithm.

    Splits a long message into chunks, ensuring:
    1. No chunk exceeds the `limit` in UTF-16 code units.
    2. No UTF-16 surrogate pairs (e.g., Emojis) are truncated.
    3. HTML tags are properly closed at the end of a chunk and reopened at the start of the next chunk.
    """
    if _utf16_len(text) <= limit:
        return [text]

    chunks: list[str] = []

    # State machine variables
    # Stack stores tuples of (tag_name, full_open_tag, full_close_tag)
    active_tags: list[tuple[str, str, str]] = []

    current_chunk = ""
    current_chunk_utf16_len = 0

    # Split text into HTML tags and text content using the strict whitelist
    parts = _TELEGRAM_TAGS_RE.split(text)

    for part in parts:
        if not part:
            continue

        is_tag = False
        if part.startswith("<") and part.endswith(">"):
            tag_match = re.match(r"</?([a-zA-Z0-9\-]+)", part)
            if tag_match:
                is_tag = True
                is_close = part.startswith("</")
                tag_name = tag_match.group(1).lower()

                part_len = _utf16_len(part)

                # Calculate what the stack WOULD look like
                new_active_tags = list(active_tags)
                if is_close:
                    for i in range(len(new_active_tags) - 1, -1, -1):
                        if new_active_tags[i][0] == tag_name:
                            new_active_tags.pop(i)
                            break
                else:
                    close_tag = f"</{tag_name}>"
                    new_active_tags.append((tag_name, part, close_tag))

                new_closing_length = sum(_utf16_len(t[2]) for t in new_active_tags)

                if current_chunk_utf16_len + part_len + new_closing_length > limit and current_chunk:
                    # Need to split BEFORE adding this tag
                    # Close tags using the CURRENT stack (before this tag is added)
                    close_tags_str = "".join(t[2] for t in reversed(active_tags))
                    chunks.append(current_chunk + close_tags_str)

                    # Start new chunk
                    # The new chunk starts with the tags that WOULD be open AFTER this tag is added
                    # Wait, if we start a new chunk, the current tag `part` should be the first thing AFTER the open tags?
                    # Actually, if we split BEFORE this tag, the open tags at the start of the new chunk should be the CURRENT stack.
                    # Then we add this tag to the new chunk.
                    open_tags_str = "".join(t[1] for t in active_tags)
                    current_chunk = open_tags_str + part
                    current_chunk_utf16_len = _utf16_len(current_chunk)

                    # Update the stack to the new state
                    active_tags = new_active_tags
                else:
                    current_chunk += part
                    current_chunk_utf16_len += part_len
                    active_tags = new_active_tags

        if not is_tag:
            # Handle text content
            text_part = part
            while text_part:
                closing_length = sum(_utf16_len(t[2]) for t in active_tags)
                available_space = limit - current_chunk_utf16_len - closing_length

                if available_space <= 0:
                    if not current_chunk:
                        # Edge case: limit is too small even for tags
                        # Force add one character to avoid infinite loop
                        char = text_part[0]
                        current_chunk += char
                        current_chunk_utf16_len += _utf16_len(char)
                        text_part = text_part[1:]
                        continue

                    close_tags_str = "".join(t[2] for t in reversed(active_tags))
                    chunks.append(current_chunk + close_tags_str)

                    open_tags_str = "".join(t[1] for t in active_tags)
                    current_chunk = open_tags_str
                    current_chunk_utf16_len = _utf16_len(current_chunk)
                    continue

                # Find how many characters fit in available_space
                guess_len = min(len(text_part), available_space)
                sub_text = text_part[:guess_len]
                while _utf16_len(sub_text) > available_space and guess_len > 0:
                    guess_len -= 1
                    sub_text = text_part[:guess_len]

                if guess_len == 0:
                    # A single character (like an Emoji) might take 2 UTF-16 units
                    # If available_space is 1, it won't fit. Force split.
                    close_tags_str = "".join(t[2] for t in reversed(active_tags))
                    chunks.append(current_chunk + close_tags_str)

                    open_tags_str = "".join(t[1] for t in active_tags)
                    current_chunk = open_tags_str
                    current_chunk_utf16_len = _utf16_len(current_chunk)
                    continue

                # Smart Semantic Breakpoints (Fallback Search)
                force_split = False
                if guess_len < len(text_part):
                    force_split = True
                    split_at_idx = -1
                    min_acceptable_split = max(0, len(sub_text) - 1000)  # Only search in the last 1000 chars

                    # 1. Paragraph boundary
                    p_idx = sub_text.rfind("\n\n")
                    if p_idx >= min_acceptable_split:
                        split_at_idx = p_idx + 2  # Include both \n

                    # 2. Sentence boundary
                    if split_at_idx == -1:
                        for punct in [
                            ". ",
                            "。 ",
                            "! ",
                            "！ ",
                            "? ",
                            "？ ",
                            ".\n",
                            "。\n",
                            "!\n",
                            "！\n",
                            "?\n",
                            "？\n",
                        ]:
                            p_idx = sub_text.rfind(punct)
                            if p_idx >= min_acceptable_split and (p_idx + len(punct)) > split_at_idx:
                                split_at_idx = p_idx + len(punct)

                    # 3. Newline
                    if split_at_idx == -1:
                        p_idx = sub_text.rfind("\n")
                        if p_idx >= min_acceptable_split:
                            split_at_idx = p_idx + 1

                    # 4. Space
                    if split_at_idx == -1:
                        p_idx = sub_text.rfind(" ")
                        if p_idx >= min_acceptable_split:
                            split_at_idx = p_idx + 1

                    if split_at_idx > 0:
                        # Include the boundary character(s) in the current chunk
                        sub_text = text_part[:split_at_idx]
                        guess_len = split_at_idx

                current_chunk += sub_text
                current_chunk_utf16_len += _utf16_len(sub_text)
                text_part = text_part[guess_len:]

                if force_split:
                    close_tags_str = "".join(t[2] for t in reversed(active_tags))
                    chunks.append(current_chunk + close_tags_str)

                    open_tags_str = "".join(t[1] for t in active_tags)
                    current_chunk = open_tags_str
                    current_chunk_utf16_len = _utf16_len(current_chunk)

    if current_chunk:
        # Close any remaining tags
        close_tags_str = "".join(t[2] for t in reversed(active_tags))
        chunks.append(current_chunk + close_tags_str)

    return chunks
