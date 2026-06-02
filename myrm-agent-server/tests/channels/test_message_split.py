"""Tests for smart message splitting."""

from __future__ import annotations

from app.channels.rendering.splitter import split_message


def test_short_message_no_split() -> None:
    assert split_message("hello world", 100) == ["hello world"]


def test_split_at_paragraph_boundary() -> None:
    text = "A" * 50 + "\n\n" + "B" * 50
    chunks = split_message(text, 60)
    assert len(chunks) == 2
    assert chunks[0] == "A" * 50
    assert chunks[1] == "B" * 50


def test_split_at_line_boundary() -> None:
    text = "A" * 50 + "\n" + "B" * 50
    chunks = split_message(text, 60)
    assert len(chunks) == 2
    assert chunks[0] == "A" * 50
    assert chunks[1] == "B" * 50


def test_preserves_code_block_integrity() -> None:
    code_block = "```python\nprint('hello')\n```"
    text = "Before\n\n" + code_block + "\n\nAfter some more text that is long"
    chunks = split_message(text, 30)
    joined = "\n".join(chunks)
    assert "```python" in joined
    assert "```" in joined


def test_hard_cut_when_no_boundary() -> None:
    text = "A" * 200
    chunks = split_message(text, 100)
    assert len(chunks) == 2
    assert chunks[0] == "A" * 100
    assert chunks[1] == "A" * 100


def test_does_not_split_inside_code_fence() -> None:
    code = "```\nline1\nline2\nline3\nline4\n```"
    text = f"intro\n\n{code}\n\noutro that extends a bit"
    # max_len large enough to hold the code block in one chunk
    chunks = split_message(text, 50)
    for chunk in chunks:
        fence_count = chunk.count("```")
        assert fence_count % 2 == 0 or fence_count == 0, f"Unbalanced fences in chunk: {chunk!r}"


def test_split_before_code_block_when_possible() -> None:
    text = "A" * 30 + "\n\n```\ncode\n```\n\nB" * 5
    chunks = split_message(text, 40)
    assert chunks[0].startswith("A" * 30)
    for chunk in chunks:
        fence_count = chunk.count("```")
        assert fence_count % 2 == 0, f"Unbalanced fences in chunk: {chunk!r}"


def test_empty_string() -> None:
    assert split_message("", 100) == [""]


def test_exact_max_len() -> None:
    text = "A" * 100
    assert split_message(text, 100) == [text]


def test_sentence_boundary_split() -> None:
    text = "First sentence. Second sentence. Third sentence that is quite long and extends beyond the limit."
    chunks = split_message(text, 50)
    assert len(chunks) >= 2
    assert all(len(c) <= 50 for c in chunks)
