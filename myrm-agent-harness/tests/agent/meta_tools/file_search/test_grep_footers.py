"""End-to-end tests for what a grep result says about the search itself, once per search tier.

Covers:
- The Python tier states how many files it searched: the files looked at, not only those with a hit
- The ripgrep tier states no count, because before version 15 its --json summary counts only the files that produced output
- The Python tier says when its file cap cut the scan short
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.agent.meta_tools.file_search.search_probe import SearchRunner, write_tree


@pytest.mark.parametrize("engine", ["python"], indirect=True)
class TestPythonTierFilesSearched:
    async def test_no_match_footer_counts_the_files_searched(self, plain_dir: Path, run_grep: SearchRunner) -> None:
        write_tree(plain_dir, {f"f{index}.txt": "nothing\n" for index in range(5)})

        output = await run_grep(plain_dir, "needle")

        assert "(Searched 5 file(s))" in output

    async def test_match_header_counts_the_files_searched(self, plain_dir: Path, run_grep: SearchRunner) -> None:
        write_tree(plain_dir, {f"f{index}.txt": "nothing\n" for index in range(4)} | {"hit.txt": "needle\n"})

        output = await run_grep(plain_dir, "needle")

        assert "Found 1 match(es) for 'needle' (searched 5 file(s)):" in output


@pytest.mark.parametrize("engine", ["ripgrep"], indirect=True)
class TestRipgrepTierStatesNoCount:
    async def test_no_match_result_states_no_count(self, plain_dir: Path, run_grep: SearchRunner) -> None:
        write_tree(plain_dir, {f"f{index}.txt": "nothing\n" for index in range(5)})

        output = await run_grep(plain_dir, "needle")

        assert output == "No matches found for: needle"

    async def test_header_states_no_count(self, plain_dir: Path, run_grep: SearchRunner) -> None:
        write_tree(plain_dir, {f"f{index}.txt": "nothing\n" for index in range(4)} | {"hit.txt": "needle\n"})

        output = await run_grep(plain_dir, "needle")

        assert output.splitlines()[0] == "Found 1 match(es) for 'needle':"

    async def test_header_is_the_same_when_the_cap_stops_ripgrep_early(
        self, plain_dir: Path, run_grep: SearchRunner
    ) -> None:
        write_tree(plain_dir, {f"f{index}.txt": "needle\n" for index in range(5)})

        output = await run_grep(plain_dir, "needle", max_results=2)

        assert output.splitlines()[0] == "Found 2 match(es) for 'needle':"


@pytest.mark.parametrize("engine", ["python"], indirect=True)
class TestPythonTierFileCap:
    async def test_note_tells_that_the_scan_was_cut_short(self, plain_dir: Path, run_grep: SearchRunner) -> None:
        write_tree(plain_dir, {f"f{index}.txt": "needle\n" for index in range(5)})

        output = await run_grep(plain_dir, "needle", max_files=3)

        assert output.endswith("... (scan limited to the first 3 files; narrow path or file_pattern to cover the rest)")

    async def test_note_also_follows_a_search_without_matches(self, plain_dir: Path, run_grep: SearchRunner) -> None:
        write_tree(plain_dir, {f"f{index}.txt": "nothing\n" for index in range(5)})

        output = await run_grep(plain_dir, "needle", max_files=3)

        assert "(Searched 3 file(s))" in output
        assert "scan limited to the first 3 files" in output

    async def test_no_note_when_every_file_was_scanned(self, plain_dir: Path, run_grep: SearchRunner) -> None:
        write_tree(plain_dir, {f"f{index}.txt": "needle\n" for index in range(3)})

        output = await run_grep(plain_dir, "needle", max_files=3)

        assert "scan limited" not in output
