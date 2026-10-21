"""Unit tests: revert diff truncation contract (size guard + stats)."""

from __future__ import annotations

from app.api.files.revert import (
    MAX_DIFF_CONTENT_BYTES,
    FileDiffItem,
    _build_diff_item,
    _diff_stats,
    _is_oversized,
)


class TestDiffStats:
    def test_empty_inputs(self) -> None:
        assert _diff_stats(None, None) == (0, 0)

    def test_counts_additions_and_deletions(self) -> None:
        additions, deletions = _diff_stats("a\nb\nc\n", "a\nx\nc\nd\n")
        assert additions == 2
        assert deletions == 1

    def test_identical_content(self) -> None:
        assert _diff_stats("a\n", "a\n") == (0, 0)


class TestOversized:
    def test_small_content_not_oversized(self) -> None:
        assert _is_oversized("a\n", "b\n") is False

    def test_large_content_oversized(self) -> None:
        big = "x\n" * (MAX_DIFF_CONTENT_BYTES // 2 + 100)
        assert _is_oversized(big, big) is True


class TestBuildDiffItem:
    def test_normal_file_returns_content_with_stats(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        target = tmp_path / "demo.txt"
        target.write_text("a\nb\n", encoding="utf-8")
        item = _build_diff_item(str(target), "modify", "a\n")
        assert isinstance(item, FileDiffItem)
        assert item.truncated is False
        assert item.is_binary is False
        assert item.current == "a\nb\n"
        assert (item.additions, item.deletions) == (1, 0)

    def test_oversized_file_truncated_without_content(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        target = tmp_path / "big.txt"
        target.write_bytes(b"y\n" * (MAX_DIFF_CONTENT_BYTES // 2 + 100))
        item = _build_diff_item(str(target), "modify", "y\n")
        assert item.truncated is True
        assert item.original is None
        assert item.current is None
