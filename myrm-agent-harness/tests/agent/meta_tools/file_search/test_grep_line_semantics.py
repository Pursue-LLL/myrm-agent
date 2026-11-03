"""End-to-end tests for how grep reads a line, once per search tier.

Covers:
- ``context_lines`` surrounds every match with its neighbours, merges overlapping windows and stops at file edges
- A line is matched without its line ending only: ``$`` does not see through trailing whitespace or a carriage return
- A search of one file names that file in its result
"""

from __future__ import annotations

from pathlib import Path

from tests.agent.meta_tools.file_search.search_probe import SearchRunner, write_tree


def _rows(output: str) -> list[str]:
    """The result rows without the header, with the trailing whitespace ripgrep keeps and the Python tier drops."""
    return [row.rstrip() for row in output.split("\n")[2:]]


class TestContextLines:
    async def test_every_match_is_surrounded_by_its_neighbours(self, plain_dir: Path, run_grep: SearchRunner) -> None:
        write_tree(plain_dir, {"ctx.txt": "1\n2\nneedle\n4\n5\n6\n7\nneedle\n9\n"})

        output = await run_grep(plain_dir, "needle", context_lines=1)

        assert _rows(output) == [
            "ctx.txt-2- 2",
            "ctx.txt:3: needle",
            "ctx.txt-4- 4",
            "--",
            "ctx.txt-7- 7",
            "ctx.txt:8: needle",
            "ctx.txt-9- 9",
        ]

    async def test_overlapping_windows_share_their_lines(self, plain_dir: Path, run_grep: SearchRunner) -> None:
        write_tree(plain_dir, {"adj.txt": "a\nneedle\nneedle\nb\nneedle\nc\n"})

        output = await run_grep(plain_dir, "needle", context_lines=1)

        assert _rows(output) == [
            "adj.txt-1- a",
            "adj.txt:2: needle",
            "adj.txt:3: needle",
            "adj.txt-4- b",
            "adj.txt:5: needle",
            "adj.txt-6- c",
        ]

    async def test_windows_stop_at_the_edges_of_the_file(self, plain_dir: Path, run_grep: SearchRunner) -> None:
        # No newline after the last line: it is still a line.
        (plain_dir / "edge.txt").write_bytes(b"needle\nm1\nm2\nm3\nneedle")

        output = await run_grep(plain_dir, "needle", context_lines=2)

        assert _rows(output) == [
            "edge.txt:1: needle",
            "edge.txt-2- m1",
            "edge.txt-3- m2",
            "edge.txt-4- m3",
            "edge.txt:5: needle",
        ]

    async def test_context_never_comes_from_a_neighbouring_file(self, plain_dir: Path, run_grep: SearchRunner) -> None:
        write_tree(plain_dir, {"a.txt": "needle\n", "b.txt": "x\n"})

        output = await run_grep(plain_dir, "needle", context_lines=3)

        assert _rows(output) == ["a.txt:1: needle"]


class TestLineEnding:
    async def test_dollar_anchor_does_not_see_through_trailing_whitespace(
        self, plain_dir: Path, run_grep: SearchRunner
    ) -> None:
        write_tree(plain_dir, {"ws.txt": "foo\nfoo   \nbar\n"})

        assert _rows(await run_grep(plain_dir, "foo$")) == ["ws.txt:1: foo"]

    async def test_pattern_can_match_the_trailing_whitespace(self, plain_dir: Path, run_grep: SearchRunner) -> None:
        write_tree(plain_dir, {"ws.txt": "foo\nfoo   \nbar\n"})

        assert _rows(await run_grep(plain_dir, r"foo\s+$")) == ["ws.txt:2: foo"]

    async def test_dollar_anchor_does_not_match_before_a_carriage_return(
        self, plain_dir: Path, run_grep: SearchRunner
    ) -> None:
        (plain_dir / "crlf.txt").write_bytes(b"x\r\nneedle\r\ny\r\n")

        output = await run_grep(plain_dir, "needle$")

        assert output.startswith("No matches found")


class TestSingleFileSearch:
    async def test_the_result_names_the_file(self, plain_dir: Path, run_grep: SearchRunner) -> None:
        write_tree(plain_dir, {"only.txt": "needle\n", "other.txt": "needle\n"})

        output = await run_grep(plain_dir, "needle", path="only.txt")

        assert _rows(output) == ["only.txt:1: needle"]
