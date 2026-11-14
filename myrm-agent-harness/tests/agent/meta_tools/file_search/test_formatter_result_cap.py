"""Tests for the result cap and the file order of the grep result formatter."""

from __future__ import annotations

from myrm_agent_harness.agent.meta_tools.file_search._formatter import format_grep_results

type Rows = list[dict[str, str | int]]


def _match(file: str, line: int, content: str = "match", kind: str = "match") -> dict[str, str | int]:
    return {"file": file, "line": line, "content": content, "type": kind}


class TestResultCap:
    """A caller hands over one match beyond the cap: it shows the cap cut the search short, and is not shown."""

    def test_a_match_beyond_the_cap_is_cut_and_noted(self) -> None:
        results: Rows = [_match("a.py", line, f"match {line}") for line in range(1, 7)]

        output = format_grep_results(results, "match", 10, 5)

        assert "Found 5 match(es)" in output
        assert "match 5" in output
        assert "match 6" not in output
        assert output.endswith("\n... (limited to first 5 results)")

    def test_exactly_the_cap_is_complete_and_not_noted(self) -> None:
        results: Rows = [_match("a.py", line, f"match {line}") for line in range(1, 6)]

        output = format_grep_results(results, "match", 10, 5)

        assert "Found 5 match(es)" in output
        assert "match 5" in output
        assert "limited" not in output

    def test_fewer_than_the_cap_is_not_noted(self) -> None:
        output = format_grep_results([_match("a.py", 1)], "match", 10, 5)

        assert "limited" not in output

    def test_output_ends_at_the_last_shown_match(self) -> None:
        results: Rows = [
            _match("a.py", 1, "first"),
            _match("a.py", 2, "after first", kind="context"),
            _match("a.py", 3, "second"),
            _match("a.py", 4, "after second", kind="context"),
            _match("a.py", 9, "third"),
        ]

        output = format_grep_results(results, "x", 10, 2)

        assert "second" in output
        assert "after second" not in output
        assert "third" not in output

    def test_context_after_the_last_match_is_kept_when_the_cap_was_not_reached(self) -> None:
        results: Rows = [_match("a.py", 1, "first"), _match("a.py", 2, "after first", kind="context")]

        assert "after first" in format_grep_results(results, "x", 10, 2)

    def test_the_cap_counts_matches_not_context_rows(self) -> None:
        results: Rows = [
            _match("a.py", 1, "ctx before", kind="context"),
            _match("a.py", 2, "first"),
            _match("a.py", 3, "ctx between", kind="context"),
            _match("a.py", 4, "second"),
        ]

        output = format_grep_results(results, "x", 10, 2)

        assert "ctx between" in output
        assert "limited" not in output


class TestFileOrder:
    """Files are listed in path order whatever order the search delivered them in (ripgrep walks in parallel)."""

    def test_files_are_listed_in_path_order(self) -> None:
        results: Rows = [_match("src/b.py", 1), _match("a.py", 1), _match("src/a.py", 1)]

        output = format_grep_results(results, "match", 3, 100)

        assert output.index("a.py:1") < output.index("src/a.py:1") < output.index("src/b.py:1")

    def test_a_directory_stays_together_as_in_glob_output(self) -> None:
        # Component-wise order, the order glob_tool lists in: "a/b.py" precedes "a-b.py" although "-" sorts before "/".
        results: Rows = [_match("a-b.py", 1), _match("a/b.py", 1)]

        output = format_grep_results(results, "match", 2, 100)

        assert output.index("a/b.py:1") < output.index("a-b.py:1")

    def test_the_matches_of_a_file_stay_together_in_their_line_order(self) -> None:
        results: Rows = [_match("b.py", 3), _match("a.py", 1), _match("b.py", 7), _match("a.py", 2)]

        output = format_grep_results(results, "match", 2, 100)

        assert [line for line in output.splitlines() if ".py:" in line] == [
            "a.py:1: match",
            "a.py:2: match",
            "b.py:3: match",
            "b.py:7: match",
        ]
