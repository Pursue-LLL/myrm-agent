"""Feishu interactive-card size slicing with code-fence and table-header continuity.

Pure functions for chunking long Markdown text, which may hold tables and code blocks, into cards that each stay under
Feishu's size limit and render on their own.

[INPUT]
- Arbitrary Markdown text from LLM agent responses.

[OUTPUT]
- is_table_row: Check if a line is a Markdown table row.
- is_table_separator: Check if a line is a Markdown table separator/delimiter row.
- slice_card_markdown: Split long Markdown text into chunks that each take at most max_bytes of a card request body;
  every chunk is a self-contained document.

[POS]
Feishu Markdown payload boundary slicer with code-fence and table header replication.
"""

from __future__ import annotations

import json
import re

# Feishu rejects a card message whose request body is over 30 KB (HTTP 400, code 230025). The Markdown may take 24,000
# bytes of it; the card's own JSON, and the sources and buttons of the last card, take the rest.
DEFAULT_MAX_CARD_BYTES = 24_000

_TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
# A delimiter cell is hyphens with an optional colon on each side (GFM): ``-``, ``:--``, ``:-:``.
_TABLE_SEP_RE = re.compile(r"^\s*\|(\s*:?-+:?\s*\|)+\s*$")
# A fence line is a run of three or more backticks and an info string without backticks (CommonMark).
_FENCE_RE = re.compile(r"^(`{3,})([^`]*)$")

# What the two JSON string quotes of an empty text cost; the rest of an escaped text is the text's own size.
_EMPTY_ESCAPED_BYTES = len(json.dumps(json.dumps("")))


def is_table_row(line: str) -> bool:
    """Check if a line is a Markdown table row."""
    return bool(_TABLE_ROW_RE.match(line.strip()))


def is_table_separator(line: str) -> bool:
    """Check if a line is a Markdown table separator/delimiter row (|---|---|)."""
    return bool(_TABLE_SEP_RE.match(line.strip()))


def _request_bytes(text: str) -> int:
    """Bytes ``text`` takes in the request body: the card JSON escapes it and the request escapes that JSON again.

    A quote or a backslash takes four bytes, a newline three, so Markdown full of JSON or paths outgrows its own size.
    """
    card_json = json.dumps(text, ensure_ascii=False)
    return len(json.dumps(card_json, ensure_ascii=False).encode("utf-8")) - _EMPTY_ESCAPED_BYTES


_NEWLINE_BYTES = _request_bytes("\n")


def _line_bytes(line: str) -> int:
    """Request bytes of ``line`` and the newline after it."""
    return _request_bytes(line) + _NEWLINE_BYTES


def slice_card_markdown(
    text: str,
    *,
    max_bytes: int = DEFAULT_MAX_CARD_BYTES,
) -> list[str]:
    """Slice long Markdown into multiple card-safe chunks, each rendering on its own.

    - A code block cut by a boundary is closed in its chunk and reopened, with its info string, in the next one.
    - A table cut by a boundary repeats its header and delimiter rows in the next chunk.
    - A boundary never falls between a table's header row and its delimiter row, between an opening fence and the
      first line of its block, or before a closing fence. A chunk never consists of repeated rows alone.

    Args:
        text: Full Markdown content.
        max_bytes: Most bytes a chunk may take in the request body, where JSON escaping of the card and of the request
            is counted (default: 24,000 bytes).

    Returns:
        List of chunks, each <= max_bytes unless a single line, or lines that must stay together (a table's header and
        delimiter rows, an opening fence and the first line of its block), with the rows repeated before them outgrow it.
    """
    if _request_bytes(text) <= max_bytes:
        return [text]

    lines = text.split("\n")
    weights = [_line_bytes(line) for line in lines]
    chunks: list[str] = []
    chunk: list[str] = []
    chunk_bytes = 0
    has_content = False  # the chunk holds a line of ``text``, not only rows repeated from the previous chunk

    fence_opening = ""  # the line that opened the code block the next line sits in; empty outside one
    fence_closing = ""  # the backtick run that closes it
    fence_body = 0  # lines of that block before the next line
    table_header = ""  # header and delimiter rows of the table the next line continues
    table_separator = ""
    table_rows = 0  # table rows directly before the next line

    for index, line in enumerate(lines):
        stripped = line.strip()
        marker = _FENCE_RE.match(stripped)
        run, info = marker.groups() if marker else ("", "")
        in_fence = bool(fence_opening)
        opens = bool(run) and not in_fence
        closes = in_fence and bool(run) and not info.strip() and len(run) >= len(fence_closing)
        is_row = not in_fence and not opens and is_table_row(line)
        is_separator = is_row and table_rows == 1 and is_table_separator(line)

        # What the chunk must take along with ``line``: the delimiter row under a header row, the first line of
        # a block under its opening fence, and room to close the block the chunk then ends in.
        needed = weights[index]
        starts_table = is_row and table_rows == 0 and index + 1 < len(lines) and is_table_separator(lines[index + 1])
        if starts_table or (opens and index + 1 < len(lines)):
            needed += weights[index + 1]
        if opens or (in_fence and not closes):
            # A closing fence is backticks only, which JSON leaves as they are.
            needed += len(run if opens else fence_closing) + _NEWLINE_BYTES

        inseparable = is_separator or (in_fence and (closes or fence_body == 0))
        if has_content and not inseparable and chunk_bytes + needed > max_bytes:
            if in_fence:
                chunk.append(fence_closing)
            chunks.append("\n".join(chunk))
            chunk = [fence_opening] if in_fence else ([table_header, table_separator] if is_row and table_separator else [])
            chunk_bytes = sum(_line_bytes(repeated) for repeated in chunk)
            has_content = False

        chunk.append(line)
        chunk_bytes += weights[index]
        has_content = True

        if opens:
            fence_opening, fence_closing, fence_body = stripped, run, 0
        elif closes:
            fence_opening = fence_closing = ""
        elif in_fence:
            fence_body += 1
        if is_row:
            table_rows += 1
            if table_rows == 1:
                table_header, table_separator = line, ""
            elif is_separator:
                table_separator = line
        else:
            table_rows, table_header, table_separator = 0, "", ""

    if fence_opening:
        chunk.append(fence_closing)
    chunks.append("\n".join(chunk))
    return chunks
