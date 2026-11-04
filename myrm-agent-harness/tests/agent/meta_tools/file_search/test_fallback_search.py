"""Tests for fallback_search — the Python tier's content scan.

Covers:
- ``scan_lines`` matches a line without its line ending and surrounds each match with context rows
- Lines that are not UTF-8 are skipped and the scan ends at the match cap
- The slow read path (a file mmap cannot scan) gives the same rows, and a regex timeout keeps the earlier rows
- ``search_files`` counts only matches toward the result cap, never context rows
- ``search_files`` reports the files of the batches it finished, and whether the time budget cut the search short
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from myrm_agent_harness.agent.config import FileIOConfig
from myrm_agent_harness.agent.meta_tools.file_search import fallback_search
from myrm_agent_harness.agent.meta_tools.file_search.fallback_search import (
    SearchOutcome,
    mmap_search_file,
    scan_lines,
    search_files,
)
from myrm_agent_harness.agent.meta_tools.file_search.regex_validator import RegexValidator
from myrm_agent_harness.utils.errors import ToolError
from tests.agent.meta_tools.file_search.search_probe import end_time_budget_after


def _scan(data: bytes, pattern: str, *, max_matches: int = 100, context_lines: int = 0) -> list[tuple[int, str, str]]:
    regex = re.compile(pattern)
    lines = iter(data.splitlines(keepends=True))
    rows = scan_lines(lines, regex.search, max_matches, context_lines)
    return [(int(row["line"]), str(row["type"]), str(row["content"])) for row in rows]


class TestScanLines:
    def test_a_line_is_matched_without_its_newline_only(self) -> None:
        assert _scan(b"foo\nfoo   \n", "foo$") == [(1, "match", "foo")]
        assert _scan(b"foo\nfoo   \n", r"foo\s+$") == [(2, "match", "foo")]

    def test_context_rows_surround_a_match(self) -> None:
        rows = _scan(b"1\n2\nneedle\n4\n5\n", "needle", context_lines=1)
        assert rows == [(2, "context", "2"), (3, "match", "needle"), (4, "context", "4")]

    def test_a_context_row_is_reported_once(self) -> None:
        rows = _scan(b"needle\nmid\nneedle\n", "needle", context_lines=3)
        assert rows == [(1, "match", "needle"), (2, "context", "mid"), (3, "match", "needle")]

    def test_no_context_rows_without_context_lines(self) -> None:
        assert _scan(b"1\nneedle\n3\n", "needle") == [(2, "match", "needle")]

    def test_scan_ends_at_the_cap_without_trailing_context(self) -> None:
        rows = _scan(b"needle\nafter\nneedle\n", "needle", max_matches=1, context_lines=2)
        assert rows == [(1, "match", "needle")]

    def test_lines_that_are_not_utf8_are_skipped_but_counted(self) -> None:
        assert _scan(b"\xff\xfe\nneedle\n", "needle") == [(2, "match", "needle")]

    def test_the_last_line_needs_no_newline(self) -> None:
        assert _scan(b"a\nneedle", "needle") == [(2, "match", "needle")]


class TestMmapSearchFile:
    def test_context_lines_are_returned_with_their_type(self, tmp_path: Path) -> None:
        target = tmp_path / "f.txt"
        target.write_text("a\nneedle\nb\n", encoding="utf-8")

        rows = mmap_search_file(target, re.compile("needle"), context_lines=1)

        assert [(row["line"], row["type"]) for row in rows] == [(1, "context"), (2, "match"), (3, "context")]


def _validator() -> RegexValidator:
    return RegexValidator(FileIOConfig())


async def _run(files: list[Path], root: Path, pattern: str, **kwargs: int) -> SearchOutcome:
    options = {"max_results": 100, "context_lines": 0} | kwargs
    return await search_files(
        files, re.compile(pattern), root, regex_validator=_validator(), timeout_seconds=10.0, **options
    )


async def _search(files: list[Path], root: Path, pattern: str, **kwargs: int) -> list[dict[str, str | int]]:
    return (await _run(files, root, pattern, **kwargs)).rows


class TestSlowReadPath:
    @pytest.fixture
    def mmap_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def broken(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("mmap unavailable")

        monkeypatch.setattr(fallback_search, "mmap_search_file", broken)

    async def test_rows_match_those_of_the_mmap_path(self, tmp_path: Path, mmap_unavailable: None) -> None:
        target = tmp_path / "f.txt"
        target.write_bytes(b"1\nfoo   \nneedle\n4\n")

        rows = await _search([target], tmp_path, r"needle|foo$", context_lines=1)

        assert [(row["file"], row["line"], row["type"]) for row in rows] == [
            ("f.txt", 2, "context"),
            ("f.txt", 3, "match"),
            ("f.txt", 4, "context"),
        ]

    async def test_a_regex_timeout_keeps_the_rows_found_before_it(
        self, tmp_path: Path, mmap_unavailable: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "f.txt"
        target.write_bytes(b"needle\nslow\nneedle\n")
        validator = _validator()
        real_search = validator.safe_search

        def safe_search(regex: re.Pattern[str], text: str, timeout: float | None = None) -> re.Match[str] | None:
            if text == "slow":
                raise ToolError(message="timeout", user_hint="timeout")
            return real_search(regex, text, timeout)

        monkeypatch.setattr(validator, "safe_search", safe_search)
        outcome = await search_files(
            [target],
            re.compile("needle"),
            tmp_path,
            regex_validator=validator,
            max_results=100,
            timeout_seconds=10.0,
        )

        assert [row["line"] for row in outcome.rows] == [1]


class TestResultCap:
    async def test_context_rows_do_not_use_up_the_cap(self, tmp_path: Path) -> None:
        crowded = tmp_path / "a.txt"
        crowded.write_text("1\n2\nneedle\n4\n5\n", encoding="utf-8")
        other = tmp_path / "b.txt"
        other.write_text("needle\n", encoding="utf-8")

        rows = await _search([crowded, other], tmp_path, "needle", max_results=2, context_lines=2)

        assert {str(row["file"]) for row in rows if row["type"] == "match"} == {"a.txt", "b.txt"}


def _write_files(root: Path, count: int, content: str) -> list[Path]:
    files = [root / f"f{index:02d}.txt" for index in range(count)]
    for file in files:
        file.write_text(content, encoding="utf-8")
    return files


class TestFilesSearched:
    # More files than one batch holds.
    FILE_COUNT = 45

    async def test_counts_every_file_of_a_search_that_finishes(self, tmp_path: Path) -> None:
        files = _write_files(tmp_path, self.FILE_COUNT, "nothing\n")

        outcome = await _run(files, tmp_path, "needle")

        assert (outcome.files_searched, outcome.timed_out) == (self.FILE_COUNT, False)

    async def test_counts_the_files_of_the_batches_finished_when_time_runs_out(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        files = _write_files(tmp_path, self.FILE_COUNT, "needle\n")
        end_time_budget_after(monkeypatch, batches=1)

        outcome = await _run(files, tmp_path, "needle")

        assert outcome.timed_out
        assert outcome.files_searched == len(outcome.rows) < self.FILE_COUNT

    async def test_counts_nothing_when_time_runs_out_before_the_first_batch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        files = _write_files(tmp_path, self.FILE_COUNT, "needle\n")
        end_time_budget_after(monkeypatch, batches=0)

        outcome = await _run(files, tmp_path, "needle")

        assert (outcome.rows, outcome.files_searched, outcome.timed_out) == ([], 0, True)

    async def test_reaching_the_result_cap_is_not_a_timeout(self, tmp_path: Path) -> None:
        files = _write_files(tmp_path, self.FILE_COUNT, "needle\n")

        outcome = await _run(files, tmp_path, "needle", max_results=3)

        assert not outcome.timed_out
        assert 0 < outcome.files_searched < self.FILE_COUNT
