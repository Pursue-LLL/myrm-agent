"""End-to-end tests: a search path that exists but cannot be read is an error, not an empty result.

Below the search root an entry the search cannot examine is skipped (test_search_unreadable_entries.py). The path the
search is aimed at gets no such treatment: ripgrep ends a run whose root it cannot open with status 2 after printing
its closing summary event, and the Python tier lists nothing, so both tiers would answer "no match" for a search that
never looked.

Covers:
- A file that cannot be opened, named as the path of grep_tool; glob_tool, which lists directories, still rejects it as
  not a directory
- A refusal that carries EPERM, as macOS privacy folders do, still reads as permission denied to the loop guard,
  and says why in the operating system's words, naming the path as the caller wrote it
- A directory that can be entered but not listed, one that can be listed but not entered, and one that is neither,
  as the path of either tool
- A path beneath a directory without search permission, whether ``Path.exists`` raises for it or answers False
- The controls: a readable path of the same kind is searched, and a file named inside a directory that can be entered
  but not listed is still found
"""

from __future__ import annotations

import errno
import os
from collections.abc import Callable
from pathlib import Path

import pytest

from myrm_agent_harness.agent.meta_tools.file_search.search_target import require_examinable_target
from myrm_agent_harness.agent.security.guards.loop_guard.suggestions.core import analyze_error_pattern
from myrm_agent_harness.agent.security.guards.loop_guard.types import ErrorPattern
from myrm_agent_harness.utils.errors import ToolError
from tests.agent.meta_tools.file_search.search_probe import SearchRunner, hit_files, listed, write_tree

Restrict = Callable[[Path, int], None]


class TestUnreadableFile:
    async def test_grep_names_the_failure(
        self, tmp_path: Path, restrict_mode: Restrict, run_grep: SearchRunner
    ) -> None:
        write_tree(tmp_path, {"locked.txt": "needle\n"})
        restrict_mode(tmp_path / "locked.txt", 0o000)

        with pytest.raises(ToolError, match=r"Permission denied: cannot read locked\.txt"):
            await run_grep(tmp_path, "needle", path="locked.txt")

    async def test_glob_still_rejects_it_as_not_a_directory(
        self, tmp_path: Path, restrict_mode: Restrict, run_glob: SearchRunner
    ) -> None:
        write_tree(tmp_path, {"locked.txt": "needle\n"})
        restrict_mode(tmp_path / "locked.txt", 0o000)

        with pytest.raises(ToolError, match=r"Not a directory: locked\.txt"):
            await run_glob(tmp_path, "*", path="locked.txt")

    async def test_a_readable_file_is_searched(self, tmp_path: Path, run_grep: SearchRunner) -> None:
        write_tree(tmp_path, {"open.txt": "needle\n"})

        assert hit_files(await run_grep(tmp_path, "needle", path="open.txt"), {"open.txt"}) == {"open.txt"}


class TestTheRefusalIsExplained:
    """A refusal that carries EPERM, with a requested path that differs from the resolved one."""

    @pytest.fixture
    def refusal(self, monkeypatch: pytest.MonkeyPatch) -> ToolError:
        def refuse(path: object, *args: object, **kwargs: object) -> os.stat_result:
            raise PermissionError(errno.EPERM, os.strerror(errno.EPERM))

        with monkeypatch.context() as patched:
            patched.setattr(os, "stat", refuse)
            with pytest.raises(ToolError) as caught:
                require_examinable_target("/private/privacy", "~/Library/Mail", reads_a_file=True)
        return caught.value

    def test_loop_guard_reads_it_as_permission_denied(self, refusal: ToolError) -> None:
        assert analyze_error_pattern(refusal.format_for_llm()) is ErrorPattern.PERMISSION_DENIED

    def test_it_gives_the_systems_reason_and_names_only_the_requested_path(self, refusal: ToolError) -> None:
        text = refusal.format_for_llm()

        assert os.strerror(errno.EPERM) in text
        assert "~/Library/Mail" in text
        assert "/private/privacy" not in text


class TestAPathThatCannotExist:
    @pytest.mark.parametrize("name", ["missing", "bad\x00name"], ids=["absent", "nul_byte"])
    def test_it_is_reported_as_not_found(self, tmp_path: Path, name: str) -> None:
        with pytest.raises(ToolError, match="Path not found"):
            require_examinable_target(str(tmp_path / name), name, reads_a_file=True)


class TestUnusableDirectory:
    @pytest.mark.parametrize("mode", [0o111, 0o444, 0o000], ids=["enter_only", "list_only", "closed"])
    async def test_both_tools_name_the_failure(
        self, tmp_path: Path, restrict_mode: Restrict, run_glob: SearchRunner, run_grep: SearchRunner, mode: int
    ) -> None:
        write_tree(tmp_path, {"locked/inside.txt": "needle\n"})
        restrict_mode(tmp_path / "locked", mode)

        with pytest.raises(ToolError, match="Permission denied: cannot read locked"):
            await run_grep(tmp_path, "needle", path="locked")
        with pytest.raises(ToolError, match="Permission denied: cannot read locked"):
            await run_glob(tmp_path, "**/*.txt", path="locked")

    async def test_a_readable_directory_is_searched(
        self, tmp_path: Path, run_glob: SearchRunner, run_grep: SearchRunner
    ) -> None:
        write_tree(tmp_path, {"open/inside.txt": "needle\n"})

        assert hit_files(await run_grep(tmp_path, "needle", path="open"), {"inside.txt"}) == {"inside.txt"}
        assert listed(await run_glob(tmp_path, "**/*.txt", path="open")) == {"inside.txt"}


class TestBeneathAnUnsearchableDirectory:
    async def test_the_call_fails_instead_of_reporting_nothing(
        self, tmp_path: Path, restrict_mode: Restrict, run_grep: SearchRunner
    ) -> None:
        write_tree(tmp_path, {"closed/inside.txt": "needle\n"})
        restrict_mode(tmp_path / "closed", 0o000)

        with pytest.raises(ToolError, match=r"Permission denied: cannot read closed/inside\.txt"):
            await run_grep(tmp_path, "needle", path="closed/inside.txt")

    def test_permission_is_read_from_stat_not_from_exists(
        self, tmp_path: Path, restrict_mode: Restrict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_tree(tmp_path, {"closed/inside.txt": "needle\n"})
        restrict_mode(tmp_path / "closed", 0o000)
        monkeypatch.setattr(Path, "exists", lambda path: os.path.exists(path))  # what Python 3.14 does

        with pytest.raises(ToolError, match=r"Permission denied: cannot read closed/inside\.txt"):
            require_examinable_target(str(tmp_path / "closed" / "inside.txt"), "closed/inside.txt", reads_a_file=True)

    async def test_a_file_named_inside_an_enterable_directory_is_searched(
        self, tmp_path: Path, restrict_mode: Restrict, run_grep: SearchRunner
    ) -> None:
        write_tree(tmp_path, {"enterable/inside.txt": "needle\n"})
        restrict_mode(tmp_path / "enterable", 0o111)

        output = await run_grep(tmp_path, "needle", path="enterable/inside.txt")

        assert hit_files(output, {"inside.txt"}) == {"inside.txt"}
