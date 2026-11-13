"""A result cap is noted only when it cut the results short, on both search tiers and in both tools.

Covers:
- Each tool asks its search for one result beyond the cap: that extra result alone shows that more exist
- With exactly as many results as the cap, the output is complete and carries no note
- With more results than the cap, the output holds the cap's worth and says so, in English
"""

from __future__ import annotations

from pathlib import Path

from tests.agent.meta_tools.file_search.search_probe import SearchRunner, listed, write_tree


def _notes(output: str) -> list[str]:
    """The lines a tool adds below its results to say something about them, whatever the language."""
    return [line for line in output.splitlines() if line.startswith("...")]


class TestGlobResultCap:
    async def test_a_listing_longer_than_the_cap_is_cut_and_noted(
        self, plain_dir: Path, run_glob: SearchRunner
    ) -> None:
        write_tree(plain_dir, {f"f{index}.py": "" for index in range(5)})

        output = await run_glob(plain_dir, "*.py", max_results=3)

        assert len(listed(output)) == 3
        assert "Found 3 file(s)" in output
        assert output.endswith("\n... (limited to first 3 results)")

    async def test_a_listing_exactly_the_cap_is_complete_and_not_noted(
        self, plain_dir: Path, run_glob: SearchRunner
    ) -> None:
        write_tree(plain_dir, {f"f{index}.py": "" for index in range(3)})

        output = await run_glob(plain_dir, "*.py", max_results=3)

        assert len(listed(output)) == 3
        assert _notes(output) == []

    async def test_a_listing_below_the_cap_is_not_noted(self, plain_dir: Path, run_glob: SearchRunner) -> None:
        write_tree(plain_dir, {f"f{index}.py": "" for index in range(2)})

        output = await run_glob(plain_dir, "*.py", max_results=3)

        assert len(listed(output)) == 2
        assert _notes(output) == []


class TestGrepResultCap:
    async def test_matches_beyond_the_cap_are_cut_and_noted(self, plain_dir: Path, run_grep: SearchRunner) -> None:
        write_tree(plain_dir, {f"f{index}.py": "needle\n" for index in range(5)})

        output = await run_grep(plain_dir, "needle", max_results=3)

        assert "Found 3 match(es)" in output
        assert output.endswith("\n... (limited to first 3 results)")

    async def test_matches_of_one_file_beyond_the_cap_are_cut_and_noted(
        self, plain_dir: Path, run_grep: SearchRunner
    ) -> None:
        write_tree(plain_dir, {"one.py": "needle\n" * 6})

        output = await run_grep(plain_dir, "needle", max_results=3)

        assert "Found 3 match(es)" in output
        assert output.endswith("\n... (limited to first 3 results)")

    async def test_exactly_the_cap_is_complete_and_not_noted(self, plain_dir: Path, run_grep: SearchRunner) -> None:
        write_tree(plain_dir, {f"f{index}.py": "needle\n" for index in range(3)})

        output = await run_grep(plain_dir, "needle", max_results=3)

        assert "Found 3 match(es)" in output
        assert _notes(output) == []

    async def test_exactly_the_cap_in_one_file_is_complete_and_not_noted(
        self, plain_dir: Path, run_grep: SearchRunner
    ) -> None:
        write_tree(plain_dir, {"one.py": "needle\n" * 3})

        output = await run_grep(plain_dir, "needle", max_results=3)

        assert "Found 3 match(es)" in output
        assert _notes(output) == []

    async def test_the_last_match_keeps_its_context_when_no_match_was_cut(
        self, plain_dir: Path, run_grep: SearchRunner
    ) -> None:
        write_tree(plain_dir, {"one.py": "needle\nafter the first\nneedle\nafter the last\n"})

        output = await run_grep(plain_dir, "needle", context_lines=1, max_results=2)

        assert "after the last" in output
        assert _notes(output) == []

    async def test_context_after_the_last_shown_match_goes_with_the_cut_matches(
        self, plain_dir: Path, run_grep: SearchRunner
    ) -> None:
        write_tree(plain_dir, {"one.py": "needle\nafter the first\nneedle\nafter the second\nneedle\n"})

        output = await run_grep(plain_dir, "needle", context_lines=1, max_results=2)

        assert "after the first" in output
        assert "after the second" not in output
        assert output.endswith("\n... (limited to first 2 results)")
