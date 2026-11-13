"""Feishu interactive-card 28KB boundary slicing with code-fence and table-header continuity.

Pure functions for safely chunking large Markdown text containing tables and
code blocks to comply with Feishu's 28,000-byte interactive card payload limit,
ensuring code blocks and table structures remain valid across sliced card boundaries.

[INPUT]
- Arbitrary Markdown text from LLM agent responses.

[OUTPUT]
- is_table_row: Check if a line is a Markdown table row.
- is_table_separator: Check if a line is a Markdown table separator/delimiter row.
- slice_card_markdown: Split long Markdown text into chunks <= max_bytes; every chunk is a self-contained document.

[POS]
Feishu Markdown payload boundary slicer with code-fence and table header replication.
"""

from __future__ import annotations

import re

# Feishu hard limit is 28,000 bytes. 24,000 bytes reserves 4,000 bytes for card JSON envelope.
DEFAULT_MAX_CARD_BYTES = 24_000

_TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|(\s*[-:]{2,}\s*\|)+\s*$")
_CODE_FENCE_START_RE = re.compile(r"^```(\w*)")
_FENCE = "```"


def is_table_row(line: str) -> bool:
    """Check if a line is a Markdown table row."""
    return bool(_TABLE_ROW_RE.match(line.strip()))


def is_table_separator(line: str) -> bool:
    """Check if a line is a Markdown table separator/delimiter row (|---|---|)."""
    return bool(_TABLE_SEP_RE.match(line.strip()))


def _line_bytes(line: str) -> int:
    """UTF-8 size of ``line`` plus its newline."""
    return len(line.encode("utf-8")) + 1


def slice_card_markdown(
    text: str,
    *,
    max_bytes: int = DEFAULT_MAX_CARD_BYTES,
) -> list[str]:
    """Slice long Markdown into multiple card-safe chunks, each rendering on its own.

    - A code block cut by a boundary is closed in its chunk and reopened, with its language, in the next one.
    - A table cut by a boundary repeats its header and delimiter rows in the next chunk.
    - A boundary never falls between a table's header row and its delimiter row, between an opening fence and the
      first line of its block, or before a closing fence. A chunk never consists of repeated rows alone.

    Args:
        text: Full Markdown content.
        max_bytes: Maximum UTF-8 byte length allowed per chunk (default: 24,000 bytes).

    Returns:
        List of chunks, each <= max_bytes unless one line of ``text`` (with the rows repeated before it) is bigger.
    """
    if len(text.encode("utf-8")) <= max_bytes:
        return [text]

    lines = text.split("\n")
    chunks: list[str] = []
    chunk: list[str] = []
    chunk_bytes = 0
    has_content = False  # the chunk holds a line of ``text``, not only rows repeated from the previous chunk

    fence = ""  # opening line of the code block the next line sits in; empty outside one
    fence_body = 0  # lines of that block before the next line
    table_header = ""  # header and delimiter rows of the table the next line continues
    table_separator = ""
    table_rows = 0  # table rows directly before the next line

    for index, line in enumerate(lines):
        opening = _CODE_FENCE_START_RE.match(line.strip())
        in_fence = bool(fence)
        is_row = opening is None and not in_fence and is_table_row(line)
        is_separator = is_row and table_rows == 1 and is_table_separator(line)

        # What the chunk must take along with ``line``: the delimiter row under a header row, the first line of
        # a block under its opening fence, and room to close the block the chunk then ends in.
        needed = _line_bytes(line)
        starts_table = is_row and table_rows == 0 and index + 1 < len(lines) and is_table_separator(lines[index + 1])
        if starts_table or (opening is not None and not in_fence and index + 1 < len(lines)):
            needed += _line_bytes(lines[index + 1])
        if (opening is not None) != in_fence:
            needed += _line_bytes(_FENCE)

        inseparable = is_separator or (in_fence and (opening is not None or fence_body == 0))
        if has_content and not inseparable and chunk_bytes + needed > max_bytes:
            if in_fence:
                chunk.append(_FENCE)
            chunks.append("\n".join(chunk))
            chunk = [fence] if in_fence else ([table_header, table_separator] if is_row and table_separator else [])
            chunk_bytes = sum(_line_bytes(repeated) for repeated in chunk)
            has_content = False

        chunk.append(line)
        chunk_bytes += _line_bytes(line)
        has_content = True

        if opening is not None:
            fence, fence_body = ("", 0) if in_fence else (opening.group(0), 0)
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

    if fence:
        chunk.append(_FENCE)
    chunks.append("\n".join(chunk))
    return chunks
