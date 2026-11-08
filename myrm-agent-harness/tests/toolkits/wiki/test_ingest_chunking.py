"""Tests for large-document chunking on Wiki ingestion."""

from __future__ import annotations

from myrm_agent_harness.toolkits.wiki.ingest_chunking import _LARGE_DOC_CHUNK_THRESHOLD, split_if_large


class TestSplitIfLarge:
    """Tests for split_if_large chunking logic."""

    def test_small_content_returns_single_entry(self) -> None:
        content = "Short doc content"
        result = split_if_large(content, "notes/test.md")
        assert len(result) == 1
        assert result[0] == ("notes/test.md", content)

    def test_exactly_at_threshold_returns_single_entry(self) -> None:
        content = "x" * _LARGE_DOC_CHUNK_THRESHOLD
        result = split_if_large(content, "doc.md")
        assert len(result) == 1
        assert result[0] == ("doc.md", content)

    def _make_diverse_content(self, min_chars: int) -> str:
        """Generate diverse content that survives chunk quality filtering."""
        sections: list[str] = []
        i = 0
        while len("\n\n".join(sections)) < min_chars:
            sections.append(
                f"## Section {i}: Topic Alpha-{i}\n\n"
                f"Paragraph about concept {i} in domain engineering. "
                f"The framework handles request {i} through middleware layer {i}. "
                f"Configuration parameter set-{i} controls behavior for module {i}.\n"
            )
            i += 1
        return "\n\n".join(sections)

    def test_above_threshold_produces_multiple_chunks(self) -> None:
        content = self._make_diverse_content(_LARGE_DOC_CHUNK_THRESHOLD + 10000)
        assert len(content) > _LARGE_DOC_CHUNK_THRESHOLD

        result = split_if_large(content, "big_report.md")
        assert len(result) >= 2

        for path, chunk in result:
            assert path.endswith(".md")
            assert len(chunk) > 0

    def test_chunk_naming_with_parent_path(self) -> None:
        content = self._make_diverse_content(_LARGE_DOC_CHUNK_THRESHOLD + 10000)
        result = split_if_large(content, "folder/subfolder/report.md")

        if len(result) >= 2:
            for path, _ in result:
                assert path.startswith("folder/subfolder/")
                assert "report_chunk" in path

    def test_chunk_naming_without_parent(self) -> None:
        content = self._make_diverse_content(_LARGE_DOC_CHUNK_THRESHOLD + 10000)
        result = split_if_large(content, "report.md")

        if len(result) >= 2:
            for path, _ in result:
                assert "report_chunk" in path

    def test_all_content_preserved_after_split(self) -> None:
        words = [f"word{i}" for i in range(_LARGE_DOC_CHUNK_THRESHOLD // 3)]
        content = " ".join(words)
        result = split_if_large(content, "doc.md")

        combined = " ".join(chunk for _, chunk in result)
        for w in words[:50]:
            assert w in combined
