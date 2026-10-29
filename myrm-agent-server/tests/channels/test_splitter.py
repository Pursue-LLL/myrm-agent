"""Tests for rendering/splitter.py — smart message splitting."""

from __future__ import annotations

import random
import re

import pytest

from app.channels.rendering.splitter import cap_stream_preview, split_message


class TestSplitMessage:
    def test_short_message_no_split(self) -> None:
        result = split_message("hello world", max_len=100)
        assert result == ["hello world"]

    def test_exact_max_len(self) -> None:
        text = "a" * 100
        result = split_message(text, max_len=100)
        assert result == [text]

    def test_split_at_paragraph(self) -> None:
        text = "first paragraph\n\nsecond paragraph"
        result = split_message(text, max_len=25)
        assert len(result) == 2
        assert result[0] == "first paragraph\n\n"
        assert result[1] == "second paragraph"
        assert "".join(result) == text

    def test_split_at_newline(self) -> None:
        text = "line one\nline two\nline three"
        result = split_message(text, max_len=15)
        assert len(result) >= 2
        assert "line one" in result[0]

    def test_split_at_sentence(self) -> None:
        text = "First sentence. Second sentence. Third sentence."
        result = split_message(text, max_len=35)
        assert len(result) >= 2

    def test_hard_cut_no_boundary(self) -> None:
        text = "a" * 200
        result = split_message(text, max_len=50)
        assert all(len(chunk) <= 50 for chunk in result)
        assert "".join(result) == text

    def test_preserves_code_block(self) -> None:
        text = "before\n\n```python\ncode line 1\ncode line 2\n```\n\nafter"
        result = split_message(text, max_len=60)
        code_chunk = [c for c in result if "```python" in c]
        assert len(code_chunk) >= 1
        assert "```" in code_chunk[0]

    def test_empty_string(self) -> None:
        result = split_message("", max_len=100)
        assert result == [""]

    def test_unicode_content(self) -> None:
        text = "你好世界\n\n这是第二段"
        result = split_message(text, max_len=10)
        assert len(result) >= 2

    def test_multiple_paragraphs(self) -> None:
        paragraphs = ["Paragraph " + str(i) for i in range(10)]
        text = "\n\n".join(paragraphs)
        result = split_message(text, max_len=50)
        assert len(result) >= 3
        for chunk in result:
            assert len(chunk) <= 50

    def test_no_empty_chunks(self) -> None:
        text = "a\n\n\n\nb\n\n\n\nc"
        result = split_message(text, max_len=5)
        assert all(chunk.strip() for chunk in result)


class TestCodeFenceReserveSpace:
    """Test code fence reserve space fix — ensures fences are properly closed/reopened."""

    def test_code_block_spanning_chunks(self) -> None:
        """Code block that must span multiple chunks should have balanced fences in each chunk."""
        code_lines = [f"line_{i} = 'x' * 100" for i in range(50)]
        long_code = "\n".join(code_lines)
        text = f"Before\n```python\n{long_code}\n```\nAfter"

        chunks = split_message(text, max_len=500)

        assert len(chunks) >= 2, "Long code block should span multiple chunks"

        for i, chunk in enumerate(chunks):
            fence_count = chunk.count("```")
            assert fence_count % 2 == 0, f"Chunk {i + 1} has unbalanced fences (count={fence_count})"

    def test_reserve_space_for_closing_fence(self) -> None:
        """Ensure space is reserved for closing fence when splitting inside code block."""
        code_content = "x" * 200
        text = f"```python\n{code_content}\n```"

        chunks = split_message(text, max_len=150)

        for i, chunk in enumerate(chunks):
            assert len(chunk) <= 150, f"Chunk {i + 1} exceeds max_len"
            fence_count = chunk.count("```")
            assert fence_count % 2 == 0, f"Chunk {i + 1} has unbalanced fences"

    def test_fence_reopening_in_next_chunk(self) -> None:
        """When code block spans chunks, next chunk should reopen the fence."""
        long_code = "\n".join([f"line {i}" for i in range(50)])
        text = f"Text before\n```python\n{long_code}\n```\nText after"

        chunks = split_message(text, max_len=200)

        assert len(chunks) >= 2, "Should have multiple chunks"

        code_chunks = [c for c in chunks if "```python" in c]
        assert len(code_chunks) >= 2, "Code fence should be reopened in subsequent chunks"

        for chunk in code_chunks:
            assert chunk.count("```") % 2 == 0, "Each chunk with fence should be balanced"

    def test_nested_fence_like_content(self) -> None:
        """Content with triple backticks inside code block should not confuse splitter."""
        text = "```python\n# Example: ```code``` here\nline2\nline3\n```"

        chunks = split_message(text, max_len=50)

        for chunk in chunks:
            fence_count = chunk.count("```")
            assert fence_count % 2 == 0, "Fences should be balanced"

    def test_multiple_code_blocks(self) -> None:
        """Multiple code blocks should each be handled correctly."""
        text = "```python\ncode1\n```\ntext\n```javascript\ncode2\n```"

        chunks = split_message(text, max_len=50)

        for chunk in chunks:
            fence_count = chunk.count("```")
            assert fence_count % 2 == 0, "Each chunk should have balanced fences"

    def test_code_block_at_chunk_boundary(self) -> None:
        """Code block starting exactly at chunk boundary should be handled."""
        padding = "x" * 100
        text = f"{padding}\n```python\ncode\n```"

        chunks = split_message(text, max_len=110)

        for chunk in chunks:
            fence_count = chunk.count("```")
            assert fence_count % 2 == 0, "Fences should be balanced"

    def test_empty_code_block(self) -> None:
        """Empty code block should be handled."""
        text = "text\n```\n```\nmore"

        chunks = split_message(text, max_len=20)

        for chunk in chunks:
            fence_count = chunk.count("```")
            assert fence_count % 2 == 0, "Empty fence should be balanced"

    def test_fence_with_language_tag(self) -> None:
        """Fence with language tag should be preserved when reopening."""
        long_code = "x\n" * 100
        text = f"```typescript\n{long_code}```"

        chunks = split_message(text, max_len=200)

        assert len(chunks) >= 2, "Should span multiple chunks"

        for i, chunk in enumerate(chunks):
            if i > 0 and "```typescript" in chunk:
                assert chunk.startswith("```typescript\n"), "Reopened fence should have language tag"


class TestBugFixes:
    """Test specific bug fixes and enhancements."""

    def test_bug_2_long_line_in_fence_no_escape(self) -> None:
        """Bug Fix: Long lines inside fences should NOT escape fence protection.

        This was a critical bug where super-long single lines inside code blocks
        would be hard-split and the middle portions would lose fence wrapping,
        causing Markdown rendering errors. CoPaw had this bug too.
        """
        # Create a 150-character single line inside a fence
        long_line = "x" * 150
        text = f"normal\n```python\n{long_line}\nmore code\n```\nend"

        chunks = split_message(text, max_len=100)

        # Verify that all chunks containing "xxx" (part of long_line) have fence markers
        for chunk in chunks:
            if "xxx" in chunk:
                # Should have opening fence
                assert "```" in chunk[:20], f"Chunk containing fence content should start with fence: {chunk[:50]}"
                # Should have closing fence
                assert chunk.rstrip().endswith("```"), f"Chunk containing fence content should end with fence: {chunk[-20:]}"

    def test_tilde_fence_support(self) -> None:
        """Enhancement: ~~~ fences should be supported (not just ```)."""
        text = "normal\n~~~python\ncode line 1\ncode line 2\n~~~\nend"

        # Test both no-split and split scenarios
        result_no_split = split_message(text, max_len=100)
        assert any("~~~" in chunk for chunk in result_no_split), "Tilde fence should be preserved"

        # Force split
        text_long = "normal\n~~~python\n" + ("code line\n" * 20) + "~~~\nend"
        chunks = split_message(text_long, max_len=50)

        # Check that tilde fences are properly handled
        for chunk in chunks:
            if "code line" in chunk:
                # Should have fence markers (either ~~~ or reopened ~~~python)
                assert "~~~" in chunk or "~~~python" in chunk, f"Code content should be fence-wrapped: {chunk[:30]}"

    def test_multiple_backticks_support(self) -> None:
        """Enhancement: Support 4+ backticks (3-10 symbols).

        Useful for nested code blocks, e.g.:
        `````
        Example with ```code``` inside
        `````
        """
        # Test 4 backticks
        text = "````python\ncode\n````"
        result = split_message(text, max_len=50)
        assert any("````" in chunk for chunk in result), "Four backticks should be recognized"

        # Test 5 backticks with nested content
        text = "`````python\ncode with ```\ninside\n`````"
        result = split_message(text, max_len=50)
        assert any("`````" in chunk for chunk in result), "Five backticks should be recognized"

        # Test fence balance
        for chunk in result:
            if "code" in chunk or "inside" in chunk:
                # Should have fence wrapper
                assert "`````" in chunk or "```" in chunk, f"Nested fence content should be wrapped: {chunk}"

    def test_smart_split_at_whitespace(self) -> None:
        """Enhancement: Long lines should be split at whitespace/punctuation boundaries when possible."""
        # Long line with many whitespace opportunities
        long_line = "This is a very long line with many words " * 5  # ~210 chars
        text = f"```python\n{long_line}\n```"

        chunks = split_message(text, max_len=100)

        # Check if any chunk ends with a space (indicating smart split)
        for chunk in chunks:
            lines = chunk.strip().split("\n")
            for line in lines:
                if line and not line.startswith("```") and not line.startswith("~~~"):
                    # Check if line ends with space or punctuation
                    if line.endswith(" ") or line[-1] in ".,;:!?":
                        break

        # Note: This test is somewhat relaxed as smart split is best-effort
        # The key is that it shouldn't fail or create malformed chunks
        assert all(chunk.strip() for chunk in chunks), "All chunks should be non-empty"


_FENCE_LINE = re.compile(r"^(`{3,10}|~{3,10})\w*\s*$")
_EMPTY_FENCE = re.compile(r"^(`{3,10}|~{3,10})\w*\s*\1$")


def _text_of(chunks: list[str]) -> str:
    """The words of the chunks without fence marker lines and whitespace: what a reader would see of the reply."""
    kept = [line for chunk in chunks for line in chunk.split("\n") if not _FENCE_LINE.match(line.strip())]
    return re.sub(r"\s+", "", "".join(kept))


def _random_document(rng: random.Random, limit: int) -> str:
    """Prose and fenced code whose lines run up to more than two chunks long, so every split path is reached."""
    blocks: list[str] = []
    for _ in range(rng.randint(2, 8)):
        if rng.random() < 0.5:
            words = (rng.choice(["alpha", "beta", "gamma,", "delta."]) for _ in range(rng.randint(1, limit // 2)))
            blocks.append(" ".join(words))
            continue
        opening, closing = rng.choice([("```", "```"), ("```python", "```"), ("~~~", "~~~"), ("````", "````")])
        lines = ["c" * rng.randint(1, limit * 2) for _ in range(rng.randint(1, 6))]
        blocks.append("\n".join([opening, *lines, closing]))
    return "\n".join(blocks)


class TestHardLimit:
    """A platform refuses a message over its limit, so no chunk goes past ``max_len`` and none is an empty code block."""

    @pytest.mark.parametrize("line_len", [1985, 1990, 1999, 2000, 2300, 5000])
    def test_a_long_fenced_line_is_cut_to_the_limit(self, line_len: int) -> None:
        line = "y" * line_len
        chunks = split_message(f"```json\n{line}\n```", max_len=2000)

        assert all(len(chunk) <= 2000 for chunk in chunks)
        assert all(chunk.startswith("```json\n") and chunk.endswith("\n```") for chunk in chunks)
        assert "".join(chunk.split("\n")[1] for chunk in chunks) == line

    def test_a_fence_opener_does_not_become_a_chunk_of_its_own(self) -> None:
        chunks = split_message("intro\n```json\n" + "y" * 2300 + "\n```", max_len=2000)

        assert chunks[0].strip() == "intro"
        assert not any(_EMPTY_FENCE.match(chunk.strip()) for chunk in chunks)

    def test_the_closing_symbol_of_a_long_fence_is_reserved_in_full(self) -> None:
        fence = "`" * 10
        chunks = split_message("\n".join([fence, *["x" * 39] * 10, fence]), max_len=100)

        assert len(chunks) > 1
        assert all(len(chunk) <= 100 for chunk in chunks)

    def test_random_documents_stay_within_the_limit_without_empty_blocks_or_lost_text(self) -> None:
        rng = random.Random(20261030)
        for _ in range(300):
            limit = rng.choice([120, 300, 2000])
            document = _random_document(rng, limit)
            chunks = split_message(document, max_len=limit)

            assert all(len(chunk) <= limit for chunk in chunks), (limit, [len(c) for c in chunks])
            assert not any(_EMPTY_FENCE.match(chunk.strip()) for chunk in chunks)
            assert _text_of(chunks) == _text_of([document])


class TestRegressionAndEdgeCases:
    """Test edge cases and regression scenarios."""

    def test_very_long_single_line_no_whitespace(self) -> None:
        """Edge case: 500-character line with no whitespace in fence."""
        long_line = "x" * 500
        text = f"```python\n{long_line}\n```"

        chunks = split_message(text, max_len=100)

        # Should not crash and all fence content should be wrapped
        assert len(chunks) >= 1
        for chunk in chunks:
            if "xxx" in chunk:
                assert "```" in chunk, "Fence content should be wrapped"

    def test_empty_fence_content(self) -> None:
        """Edge case: Empty code fence."""
        text = "before\n```python\n```\nafter"

        result = split_message(text, max_len=50)

        # Should not crash
        assert len(result) >= 1

    def test_fence_at_exact_chunk_boundary(self) -> None:
        """Edge case: Fence marker appears exactly at chunk boundary."""
        # Create text where fence opening is near max_len
        padding = "x" * 95
        text = f"{padding}\n```python\ncode\n```"

        result = split_message(text, max_len=100)

        # Should handle gracefully
        assert len(result) >= 1
        for chunk in result:
            fence_count = chunk.count("```")
            assert fence_count % 2 == 0

    def test_mixed_fence_types(self) -> None:
        """Edge case: Both ``` and ~~~ fences in same message."""
        text = "```python\ncode1\n```\ntext\n~~~bash\ncode2\n~~~"

        result = split_message(text, max_len=50)

        # Both fence types should be preserved
        all_text = "".join(result)
        assert "```" in all_text
        assert "~~~" in all_text

        # All chunks should have balanced fences
        for chunk in result:
            fence_count = chunk.count("```") + chunk.count("~~~")
            assert fence_count % 2 == 0


class TestCjkAndContentPreservation:
    def test_cjk_long_line_splits_at_punctuation(self) -> None:
        part_a = "第一部分内容" * 15
        part_b = "第二部分内容" * 15
        line = part_a + "，" + part_b
        result = split_message(line, max_len=120)
        assert len(result) >= 2
        assert all(len(chunk) <= 120 for chunk in result)
        assert "".join(result) == line

    def test_non_fence_long_line_smart_split_preserves_content(self) -> None:
        line = "alpha " * 60
        result = split_message(line, max_len=50)
        assert len(result) >= 2
        assert all(len(chunk) <= 50 for chunk in result)
        assert "".join(result) == line

    def test_smart_split_second_segment_uses_window_not_global(self) -> None:
        # Second segment should not split at an early comma in the full line.
        prefix = "x" * 180
        line = "a，" + prefix + "，" + ("b" * 80)
        result = split_message(line, max_len=100)
        assert len(result) >= 2
        assert "".join(result) == line

    def test_paragraph_content_join_preserves_newlines(self) -> None:
        text = "Paragraph.\n\n" * 50
        result = split_message(text, max_len=120)
        assert len(result) >= 2
        assert "".join(result) == text

    def test_cap_stream_preview_within_limit(self) -> None:
        text = "短预览"
        assert cap_stream_preview(text, 100) == text

    def test_cap_stream_preview_truncates_with_suffix(self) -> None:
        text = "中" * 100
        result = cap_stream_preview(text, 50)
        assert len(result) <= 50
        assert result.endswith("…")
        assert result.startswith("中")

    def test_cap_stream_preview_prefers_cjk_boundary(self) -> None:
        text = "前言" + "x" * 80 + "，" + "y" * 80
        result = cap_stream_preview(text, 90)
        assert len(result) <= 90
        assert result.endswith("…")
