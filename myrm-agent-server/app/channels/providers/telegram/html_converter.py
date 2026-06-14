"""Markdown → Telegram HTML conversion and message splitting.

Telegram HTML supports: <b>, <i>, <s>, <code>, <pre>, <a href>.
Only &, <, > need escaping in non-tag text — much simpler than MarkdownV2.

[INPUT]

[OUTPUT]
- md_to_telegram_html(): Telegram-safe HTML string with GFM table degradation
- split_message(): HTML-Aware UTF-16 safe splitting algorithm (4096 UTF-16)
- split_markdown_rich(): Markdown-aware UTF-8 safe splitting (32768 UTF-8, Bot API 10.1)

[POS]
Markdown to Telegram HTML converter. Handles bold/italic/strikethrough/code/link
and GFM table degradation (monospace ASCII tables in <pre> blocks). Supports
4096-char message splitting with state-machine-based HTML tag auto-closing and
UTF-16 surrogate pair protection. Also provides Rich Message splitting for Bot
API 10.1's native Markdown rendering path.
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
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$")

# Exact whitelist of Telegram supported HTML tags
_TELEGRAM_TAGS_RE = re.compile(
    r"(</?(?:b|strong|i|em|u|ins|s|strike|del|span|tg-spoiler|a|code|pre|blockquote|expandable)(?:\s+[^>]*)?>)",
    re.IGNORECASE,
)


def _parse_table_row(line: str) -> list[str]:
    """Split a GFM table row into stripped cell values."""
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _render_monospace_table(header_row: str, data_rows: list[str]) -> str:
    """Convert a GFM table into a ``<pre>``-wrapped monospace ASCII table."""
    headers = _parse_table_row(header_row)
    parsed_rows = [_parse_table_row(row) for row in data_rows]

    col_count = len(headers)
    for row in parsed_rows:
        while len(row) < col_count:
            row.append("")

    col_widths = [len(h) for h in headers]
    for row in parsed_rows:
        for i, cell in enumerate(row[:col_count]):
            col_widths[i] = max(col_widths[i], len(cell))

    def _fmt_row(cells: list[str]) -> str:
        padded = [cells[i].ljust(col_widths[i]) if i < len(cells) else " " * col_widths[i] for i in range(col_count)]
        return "│ " + " │ ".join(padded) + " │"

    sep_parts = ["─" * (w + 2) for w in col_widths]

    lines: list[str] = []
    lines.append("┌" + "┬".join(sep_parts) + "┐")
    lines.append(_fmt_row(headers))
    lines.append("├" + "┼".join(sep_parts) + "┤")
    for row in parsed_rows:
        lines.append(_fmt_row(row))
    lines.append("└" + "┴".join(sep_parts) + "┘")

    return "<pre>" + html.escape("\n".join(lines)) + "</pre>"


def _convert_tables(text: str) -> tuple[str, list[str]]:
    """Detect GFM tables in *text* and replace them with preserved monospace blocks.

    Returns the modified text and a list of preserved HTML blocks (to be
    appended to the caller's ``preserved`` list).
    """
    if "|" not in text or "-" not in text:
        return text, []

    lines = text.split("\n")
    out: list[str] = []
    blocks: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if (
            "|" in line
            and i + 1 < len(lines)
            and _TABLE_SEPARATOR_RE.match(lines[i + 1])
        ):
            header = line
            j = i + 2
            data_rows: list[str] = []
            while j < len(lines) and "|" in lines[j] and lines[j].strip():
                data_rows.append(lines[j])
                j += 1
            if data_rows:
                rendered = _render_monospace_table(header, data_rows)
                idx = len(blocks)
                blocks.append(rendered)
                out.append(f"\x00TBLPRESERVE{idx}\x00")
                i = j
                continue
        out.append(line)
        i += 1
    return "\n".join(out), blocks


def md_to_telegram_html(text: str) -> str:
    """Convert standard Markdown to Telegram-supported HTML subset.

    Preserves code blocks and inline code from further processing,
    then escapes HTML entities and applies formatting conversions.
    """
    preserved: list[str] = []

    def _preserve_code_block(m: re.Match[str]) -> str:
        lang, code = m.group(1), m.group(2)
        tag = (
            f'<pre><code class="language-{lang}">{html.escape(code)}</code></pre>' if lang else f"<pre>{html.escape(code)}</pre>"
        )
        preserved.append(tag)
        return f"\x00PRESERVE{len(preserved) - 1}\x00"

    def _preserve_inline_code(m: re.Match[str]) -> str:
        preserved.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00PRESERVE{len(preserved) - 1}\x00"

    result = _CODE_BLOCK_RE.sub(_preserve_code_block, text)
    result = _INLINE_CODE_RE.sub(_preserve_inline_code, result)

    result, table_blocks = _convert_tables(result)
    tbl_offset = len(preserved)
    preserved.extend(table_blocks)
    for idx in range(len(table_blocks)):
        result = result.replace(f"\x00TBLPRESERVE{idx}\x00", f"\x00PRESERVE{tbl_offset + idx}\x00")

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
        close_tags_str = "".join(t[2] for t in reversed(active_tags))
        chunks.append(current_chunk + close_tags_str)

    return chunks


# ------------------------------------------------------------------
# Rich Message splitting (Bot API 10.1 — 32768 UTF-8 characters)
# ------------------------------------------------------------------

_RICH_MAX_LENGTH = 32000  # practical limit below 32768 for headroom

_CODE_FENCE_RE = re.compile(r"^```", re.MULTILINE)


def split_markdown_rich(text: str, limit: int = _RICH_MAX_LENGTH) -> list[str]:
    """Split raw Markdown for sendRichMessage (32768 UTF-8 character limit).

    Unlike ``split_message`` which tracks HTML tags, this function splits
    plain Markdown text at semantic boundaries while preserving code fences.
    """
    if len(text.encode("utf-8")) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        byte_len = len(remaining.encode("utf-8"))
        if byte_len <= limit:
            chunks.append(remaining)
            break

        cut = _find_utf8_cut(remaining, limit)
        chunk = remaining[:cut]

        fence_count = len(_CODE_FENCE_RE.findall(chunk))
        if fence_count % 2 != 0:
            last_fence = chunk.rfind("```")
            if last_fence > 0:
                chunk = remaining[:last_fence]
                cut = last_fence

        chunks.append(chunk)
        remaining = remaining[cut:].lstrip("\n")

    return chunks


def _find_utf8_cut(text: str, byte_limit: int) -> int:
    """Find the best character index to cut at, respecting UTF-8 byte limit and semantic boundaries."""
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if len(text[:mid].encode("utf-8")) <= byte_limit:
            lo = mid
        else:
            hi = mid - 1
    max_chars = lo

    search_start = max(0, max_chars - 2000)
    window = text[search_start:max_chars]

    for sep in ["\n\n", "\n", ". ", "。", "! ", "? ", " "]:
        idx = window.rfind(sep)
        if idx >= 0:
            return search_start + idx + len(sep)

    return max_chars
