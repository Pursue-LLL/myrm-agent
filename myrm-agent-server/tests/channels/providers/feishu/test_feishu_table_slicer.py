"""Tests for Feishu table detection and card markdown slicing."""

from __future__ import annotations

from app.channels.providers.feishu.table_slicer import (
    is_table_row,
    is_table_separator,
    sanitize_lark_markdown,
    slice_card_markdown,
)


def test_table_row_and_separator_detection() -> None:
    assert is_table_row("| Name | Value |") is True
    assert is_table_row("  | a | b | c |  ") is True
    assert is_table_row("Normal text without pipe") is False

    assert is_table_separator("|---|---|") is True
    assert is_table_separator("| :--- | :---: | ---: |") is True
    assert is_table_separator("| Name | Value |") is False


def test_sanitize_lark_markdown() -> None:
    raw = "Normal text\n| Column 1 | Column 2 |\n|---|---|\n| data1 | data2 |"
    sanitized = sanitize_lark_markdown(raw)
    assert sanitized == raw


def test_slice_card_markdown_with_table_header_duplication() -> None:
    header = "| Col A | Col B | Col C |"
    sep = "|---|---|---|"
    rows = [f"| row {i} cell A | row {i} cell B | row {i} cell C |" for i in range(100)]
    full_text = "\n".join([header, sep] + rows)

    # Set small max_bytes to force slicing
    chunks = slice_card_markdown(full_text, max_bytes=500)
    assert len(chunks) > 1

    # Every continuation chunk containing table rows must contain the duplicated header and sep
    for idx, chunk in enumerate(chunks):
        if idx > 0 and "| row" in chunk:
            assert header in chunk, f"Chunk {idx} missing table header: {chunk[:100]}"
            assert sep in chunk, f"Chunk {idx} missing table separator: {chunk[:100]}"
