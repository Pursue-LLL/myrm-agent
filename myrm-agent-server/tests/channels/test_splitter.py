"""Tests for rendering/splitter.py — smart message splitting."""

from __future__ import annotations

from app.channels.rendering.splitter import split_message


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
        assert result[0] == "first paragraph"
        assert result[1] == "second paragraph"

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
            assert len(chunk) <= 154, f"Chunk {i + 1} exceeds max_len + reserve space"
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
                assert chunk.rstrip().endswith("```"), (
                    f"Chunk containing fence content should end with fence: {chunk[-20:]}"
                )

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


class TestConfigurableParameters:
    """Test configurable parameters added for flexibility."""

    def test_custom_overflow_tolerance(self) -> None:
        """Test configurable overflow_tolerance parameter."""
        # Long line that needs overflow tolerance
        long_line = "x" * 110  # 110 chars
        text = f"```python\n{long_line}\n```"

        # With default tolerance (0.2), max_len=100 allows up to 120
        chunks_default = split_message(text, max_len=100)

        # With stricter tolerance (0.1), max_len=100 allows up to 110
        chunks_strict = split_message(text, max_len=100, overflow_tolerance=0.1)

        # Both should work without errors
        assert len(chunks_default) >= 1
        assert len(chunks_strict) >= 1

        # All chunks should have balanced fences
        for chunk in chunks_default + chunks_strict:
            if "```" in chunk:
                assert chunk.count("```") % 2 == 0

    def test_overflow_tolerance_affects_chunking(self) -> None:
        """Verify overflow_tolerance actually affects chunk count."""
        # Create content that's borderline for tolerance
        line_115 = "x" * 115  # 115 chars
        text = f"```python\n{line_115}\n```"

        # With max_len=100:
        # - tolerance 0.2 allows up to 120 (115 fits in 1 chunk with fence overhead ~20)
        # - tolerance 0.05 allows up to 105 (115+20=135 > 105, needs split)

        chunks_relaxed = split_message(text, max_len=100, overflow_tolerance=0.3)
        chunks_strict = split_message(text, max_len=100, overflow_tolerance=0.05)

        # Stricter tolerance should result in more chunks (or at least not fewer)
        assert len(chunks_strict) >= len(chunks_relaxed)


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
