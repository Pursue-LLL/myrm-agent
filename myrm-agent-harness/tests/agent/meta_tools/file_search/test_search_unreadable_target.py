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
- A drive that is not ready on Windows (WinError 21) is a refusal with the system's reason, not an absent path
- A directory that can be entered but not listed, one that can be listed but not entered, and one that is neither,
  as the path of either tool
- A path beneath a directory without search permission, whether ``Path.exists`` raises for it or answers False
- A path that cannot exist (absent, below a file, a link that loops, a NUL byte, a name or a whole path beyond what the
  platform allows, and on Windows an invalid name or a link that cannot be resolved) is reported as not found, never as
  an unexpected error
- A file system that does not answer (an I/O error, a stale or timed-out network mount, a dropped FUSE mount) is
  reported as that error, never as a path that does not exist
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


class InvalidNameError(OSError):
    """What ``os.stat`` raises on Windows for an invalid name: errno EINVAL carrying WinError 123."""

    winerror = 123


class UnresolvableLinkError(OSError):
    """What ``os.stat`` raises on Windows for a link that cannot be resolved: errno EINVAL carrying WinError 1921."""

    winerror = 1921


class DriveNotReadyError(PermissionError):
    """What ``os.stat`` raises on Windows for a drive that exists but is not accessible: errno EACCES, WinError 21."""

    winerror = 21


def fail_stat_for(monkeypatch: pytest.MonkeyPatch, target: str, error: OSError) -> None:
    """Make ``os.stat`` raise ``error`` for ``target`` only; every other path gets the real answer."""
    real_stat = os.stat

    def stat(
        path: str | os.PathLike[str], *, dir_fd: int | None = None, follow_symlinks: bool = True
    ) -> os.stat_result:
        if str(path) == target:
            raise error
        return real_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(os, "stat", stat)


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

    resolved = "/private/privacy"
    requested = "~/Library/Mail"

    @pytest.fixture
    def refusal(self, monkeypatch: pytest.MonkeyPatch) -> ToolError:
        def refuse(path: object, *args: object, **kwargs: object) -> os.stat_result:
            raise PermissionError(errno.EPERM, os.strerror(errno.EPERM))

        with monkeypatch.context() as patched:
            patched.setattr(os, "stat", refuse)
            with pytest.raises(ToolError) as caught:
                require_examinable_target(self.resolved, self.requested, reads_a_file=True)
        return caught.value

    def test_loop_guard_reads_it_as_permission_denied(self, refusal: ToolError) -> None:
        assert analyze_error_pattern(refusal.format_for_llm()) is ErrorPattern.PERMISSION_DENIED

    def test_it_gives_the_systems_reason_and_names_only_the_requested_path(self, refusal: ToolError) -> None:
        text = refusal.format_for_llm()

        assert os.strerror(errno.EPERM) in text
        assert self.requested in text
        assert self.resolved not in text


class TestADriveThatIsNotReady:
    def test_it_is_a_refusal_that_gives_the_systems_reason(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = str(tmp_path / "E:")
        fail_stat_for(monkeypatch, target, DriveNotReadyError(errno.EACCES, "The device is not ready"))

        with pytest.raises(ToolError, match=r"Permission denied: cannot read E:") as caught:
            require_examinable_target(target, "E:", reads_a_file=True)

        assert "The device is not ready" in caught.value.format_for_llm()


class TestAPathThatCannotExist:
    @pytest.mark.parametrize(
        "name",
        ["missing", "bad\x00name", "x" * 300, "d/" * 3000],
        ids=["absent", "nul_byte", "name_too_long", "path_too_long"],
    )
    def test_it_is_reported_as_not_found(self, tmp_path: Path, name: str) -> None:
        with pytest.raises(ToolError, match="Path not found"):
            require_examinable_target(str(tmp_path / name), name, reads_a_file=True)

    def test_a_name_below_a_file_is_not_found(self, tmp_path: Path) -> None:
        write_tree(tmp_path, {"file.txt": "x\n"})

        with pytest.raises(ToolError, match="Path not found"):
            require_examinable_target(str(tmp_path / "file.txt" / "child"), "file.txt/child", reads_a_file=True)

    def test_a_link_that_loops_is_not_found(self, tmp_path: Path) -> None:
        try:
            (tmp_path / "loop").symlink_to("loop")
        except OSError:
            pytest.skip("symbolic links are not available")

        with pytest.raises(ToolError, match="Path not found"):
            require_examinable_target(str(tmp_path / "loop"), "loop", reads_a_file=True)

    def test_ebadf_reads_as_absent_as_pathlib_does(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        target = str(tmp_path / "gone")
        fail_stat_for(monkeypatch, target, OSError(errno.EBADF, os.strerror(errno.EBADF)))

        with pytest.raises(ToolError, match="Path not found"):
            require_examinable_target(target, "gone", reads_a_file=True)

    @pytest.mark.parametrize(
        ("error_type", "name"),
        [(InvalidNameError, "*.py"), (UnresolvableLinkError, "loop")],
        ids=["invalid_name", "unresolvable_link"],
    )
    def test_a_windows_error_that_pathlib_reads_as_absent_is_not_found(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error_type: type[OSError], name: str
    ) -> None:
        target = str(tmp_path / name)
        fail_stat_for(monkeypatch, target, error_type(errno.EINVAL, "The name cannot be used"))

        with pytest.raises(ToolError, match="Path not found"):
            require_examinable_target(target, name, reads_a_file=True)


class TestAFileSystemThatDoesNotAnswer:
    @pytest.mark.parametrize(
        "code",
        [errno.EIO, errno.ESTALE, errno.ETIMEDOUT, errno.ENOTCONN, errno.EINVAL],
        ids=["io_error", "stale_handle", "timed_out", "not_connected", "invalid_argument"],
    )
    def test_it_is_not_reported_as_an_absent_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int
    ) -> None:
        target = str(tmp_path / "mount")
        fail_stat_for(monkeypatch, target, OSError(code, os.strerror(code)))

        with pytest.raises(OSError) as caught:
            require_examinable_target(target, "mount", reads_a_file=True)

        assert caught.value.errno == code


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
