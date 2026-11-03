"""End-to-end tests for what a grep result says about the search itself, once per search tier.

Covers:
- The Python tier states how many files it searched: the files looked at, not only those with a hit
- The ripgrep tier states no count, because before version 15 its --json summary counts only the files that produced output
- The Python tier says when its file cap cut the scan short
- The Python tier says when its time limit cut the scan short, and counts only the files it finished
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.agent.meta_tools.file_search.search_probe import SearchRunner, end_time_budget_after, write_tree


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


TIME_LIMIT_NOTE = "... (search stopped at the time limit; narrow path or file_pattern to cover the rest)"
# More files than one batch of the Python tier holds.
FILE_COUNT = 45


@pytest.mark.parametrize("engine", ["python"], indirect=True)
class TestPythonTierTimeLimit:
    async def test_note_closes_a_result_with_matches(
        self, plain_dir: Path, run_grep: SearchRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_tree(plain_dir, {f"f{index:02d}.txt": "needle\n" for index in range(FILE_COUNT)})
        end_time_budget_after(monkeypatch, batches=1)

        output = await run_grep(plain_dir, "needle")

        header = re.fullmatch(
            r"Found (\d+) match\(es\) for 'needle' \(searched (\d+) file\(s\)\):", output.splitlines()[0]
        )
        assert header is not None
        # Every file holds one match, so the two counts agree only if the files searched are those of finished batches.
        assert header[1] == header[2]
        assert int(header[2]) < FILE_COUNT
        assert output.endswith(f"\n{TIME_LIMIT_NOTE}")

    async def test_note_closes_a_result_without_matches(
        self, plain_dir: Path, run_grep: SearchRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_tree(plain_dir, {f"f{index:02d}.txt": "nothing\n" for index in range(FILE_COUNT)})
        end_time_budget_after(monkeypatch, batches=1)

        output = await run_grep(plain_dir, "needle")

        no_match, searched, *notes = output.splitlines()
        assert no_match == "No matches found for: needle"
        count = re.fullmatch(r"\(Searched (\d+) file\(s\)\)", searched)
        assert count is not None
        assert 0 < int(count[1]) < FILE_COUNT
        assert notes == [TIME_LIMIT_NOTE]

    async def test_no_note_when_the_search_finished_in_time(self, plain_dir: Path, run_grep: SearchRunner) -> None:
        write_tree(plain_dir, {f"f{index:02d}.txt": "nothing\n" for index in range(FILE_COUNT)})

        output = await run_grep(plain_dir, "needle")

        assert f"(Searched {FILE_COUNT} file(s))" in output
        assert "time limit" not in output
