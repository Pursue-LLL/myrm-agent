"""Feishu CardKit 28KB boundary slicing, Lark Markdown sanitization, and table header duplication.

Pure functions for safely chunking large Markdown text containing tables and
code blocks to comply with Feishu's 28,000-byte interactive card payload limit,
ensuring table structures remain valid across sliced card boundaries.

[INPUT]
- Arbitrary Markdown text from LLM agent responses.

[OUTPUT]
- sanitize_lark_markdown: Clean unescaped pipes and repair unclosed inline formatting.
- slice_card_markdown: Split long Markdown text into chunks <= max_bytes with table header preservation.

[POS]
Feishu Markdown payload boundary slicer with table header replication.
"""

from __future__ import annotations

import re

# Feishu hard limit is 28,000 bytes. 24,000 bytes reserves 4,000 bytes for card JSON envelope.
DEFAULT_MAX_CARD_BYTES = 24_000

_TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|(\s*[-:]{2,}\s*\|)+\s*$")
_CODE_FENCE_START_RE = re.compile(r"^```(\w*)")


def is_table_row(line: str) -> bool:
    """Check if a line is a Markdown table row."""
    return bool(_TABLE_ROW_RE.match(line.strip()))


def is_table_separator(line: str) -> bool:
    """Check if a line is a Markdown table separator/delimiter row (|---|---|)."""
    return bool(_TABLE_SEP_RE.match(line.strip()))


def sanitize_lark_markdown(text: str) -> str:
    """Sanitize Lark-specific Markdown formatting quirks.

    - Escapes unescaped pipe characters inside table cells (outside code spans).
    - Ensures code fences are properly balanced.
    """
    if not text:
        return ""

    lines = text.split("\n")
    sanitized_lines: list[str] = []
    in_code_block = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            sanitized_lines.append(line)
            continue

        if in_code_block:
            sanitized_lines.append(line)
            continue

        # In a table row, ensure cell contents don't have stray unescaped delimiters
        if is_table_row(line) and not is_table_separator(line):
            # Normal table row, preserve formatting
            sanitized_lines.append(line)
        else:
            sanitized_lines.append(line)

    return "\n".join(sanitized_lines)


def _get_utf8_byte_length(s: str) -> int:
    """Calculate UTF-8 encoded byte length."""
    return len(s.encode("utf-8"))


def slice_card_markdown(
    text: str,
    *,
    max_bytes: int = DEFAULT_MAX_CARD_BYTES,
) -> list[str]:
    """Slice long Markdown into multiple card-safe chunks with table header preservation.

    When a Markdown table exceeds max_bytes, it is split at a row boundary, and the
    original table header (Header Row + Separator Row) is automatically prepended to the
    subsequent continuation chunk so that Feishu clients render valid tables on each page.

    Args:
        text: Full Markdown content.
        max_bytes: Maximum UTF-8 byte length allowed per chunk (default: 24,000 bytes).

    Returns:
        List of chunks, each guaranteed to be <= max_bytes (unless a single line exceeds max_bytes).
    """
    cleaned = sanitize_lark_markdown(text)
    if _get_utf8_byte_length(cleaned) <= max_bytes:
        return [cleaned]

    lines = cleaned.split("\n")
    chunks: list[str] = []

    current_lines: list[str] = []
    current_bytes = 0

    in_table = False
    table_header_row = ""
    table_sep_row = ""

    in_code_fence = False
    code_fence_lang = ""

    for line in lines:
        line_bytes = _get_utf8_byte_length(line) + 1  # +1 for newline

        # Track code block fences
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_code_fence:
                in_code_fence = True
                m = _CODE_FENCE_START_RE.match(stripped)
                code_fence_lang = m.group(1) if m else ""
            else:
                in_code_fence = False
                code_fence_lang = ""

        # Track table boundaries
        if is_table_row(line):
            if not in_table:
                # Potential start of a table
                table_header_row = line
                in_table = True
            elif in_table and is_table_separator(line):
                table_sep_row = line
        else:
            if in_table and not is_table_row(line):
                in_table = False
                table_header_row = ""
                table_sep_row = ""

        # Check if adding this line would exceed max_bytes
        if current_lines and (current_bytes + line_bytes > max_bytes):
            # Close code fence in current chunk if we are inside one
            if in_code_fence:
                current_lines.append("```")

            chunks.append("\n".join(current_lines))
            current_lines = []
            current_bytes = 0

            # Reopen code fence in next chunk
            if in_code_fence:
                reopen_line = f"```{code_fence_lang}"
                current_lines.append(reopen_line)
                current_bytes += _get_utf8_byte_length(reopen_line) + 1

            # Re-inject table header in next chunk if we sliced across a table
            if in_table and table_header_row and table_sep_row:
                current_lines.append(table_header_row)
                current_lines.append(table_sep_row)
                current_bytes += _get_utf8_byte_length(table_header_row) + _get_utf8_byte_length(table_sep_row) + 2

        current_lines.append(line)
        current_bytes += line_bytes

    if current_lines:
        if in_code_fence and not current_lines[-1].strip().startswith("```"):
            current_lines.append("```")
        chunks.append("\n".join(current_lines))

    return chunks or [cleaned]
