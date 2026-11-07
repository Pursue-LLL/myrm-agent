"""End-to-end tests for how glob_tool and grep_tool invoke ripgrep and what they do when it fails.

Covers:
- ripgrep ignores the user's own configuration
- A run that ended with status 2 after printing stands, an empty answer included (an unreadable directory), and is
  logged once, in ripgrep's own words naming what it skipped
- Any other failure (an unparseable pattern, flags it cannot run, a kill after printing), a timeout and a failure
  to start fall back to the Python tier, and the one log record names the cause (exit code or exception)
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

import pytest

from myrm_agent_harness.agent.meta_tools.file_search import _rg_runner, glob_tool, grep_tool
from myrm_agent_harness.agent.meta_tools.file_search._rg_runner import RgRunResult
from tests.agent.meta_tools.file_search.search_probe import SearchRunner, hit_files, listed, warnings_from, write_tree


@pytest.fixture
def locked_dir(plain_dir: Path) -> Iterator[Path]:
    """A directory ripgrep cannot open: it walks on past it and exits with status 2 once it is done."""
    if sys.platform == "win32" or os.geteuid() == 0:
        pytest.skip("directory permissions are not enforced here (Windows, or root reads every directory)")
    write_tree(plain_dir, {"locked/h.txt": "needle\n"})
    locked = plain_dir / "locked"
    locked.chmod(0)
    yield locked
    locked.chmod(0o755)


@pytest.mark.parametrize("engine", ["ripgrep"], indirect=True)
class TestRipgrepConfiguration:
    async def test_user_configuration_does_not_change_results(
        self,
        plain_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        run_glob: SearchRunner,
        run_grep: SearchRunner,
    ) -> None:
        write_tree(plain_dir, {".gitignore": "ignored.txt\n", "ignored.txt": "needle\n", "kept.txt": "needle\n"})
        config = plain_dir / "rg.conf"
        config.write_text("--no-ignore\n", encoding="utf-8")
        monkeypatch.setenv("RIPGREP_CONFIG_PATH", str(config))

        assert listed(await run_glob(plain_dir, "*.txt")) == {"kept.txt"}
        assert hit_files(await run_grep(plain_dir, "needle"), {"kept.txt", "ignored.txt"}) == {"kept.txt"}


@pytest.mark.parametrize("engine", ["ripgrep"], indirect=True)
class TestRipgrepFailureStands:
    """ripgrep's answer is used as it is: the engine fixture fails a test whose call reached the Python tier."""

    @pytest.mark.usefixtures("locked_dir")
    async def test_unreadable_directory_keeps_the_matches_already_found(
        self, plain_dir: Path, run_glob: SearchRunner, run_grep: SearchRunner
    ) -> None:
        write_tree(plain_dir, {f"ok/f{index:02d}.txt": "needle\n" for index in range(30)})

        # More matching files than the Python tier would scan, so a fallback would visibly lose matches.
        grep_output = await run_grep(plain_dir, "needle", max_files=10)
        glob_output = await run_glob(plain_dir, "**/*.txt")

        assert "Found 30 match(es)" in grep_output
        assert len(listed(glob_output)) == 30

    @pytest.mark.usefixtures("locked_dir")
    async def test_glob_with_no_match_stands_when_ripgrep_met_an_unreadable_directory(
        self, plain_dir: Path, run_glob: SearchRunner
    ) -> None:
        write_tree(plain_dir, {"ok/a.txt": "x\n"})

        assert await run_glob(plain_dir, "**/*.py") == "No files found matching: **/*.py"

    @pytest.mark.usefixtures("locked_dir")
    async def test_grep_with_no_match_stands_when_ripgrep_met_an_unreadable_directory(
        self, plain_dir: Path, run_grep: SearchRunner
    ) -> None:
        write_tree(plain_dir, {f"ok/f{index:02d}.txt": "alpha\n" for index in range(30)})

        # The Python tier would stop at 10 files and say so; ripgrep searched all of them.
        assert await run_grep(plain_dir, "needle", max_files=10) == "No matches found for: needle"

    @pytest.mark.usefixtures("locked_dir")
    @pytest.mark.parametrize("tool", ["grep", "glob"])
    async def test_a_failure_after_output_is_logged_once_and_names_what_ripgrep_skipped(
        self,
        tool: str,
        plain_dir: Path,
        caplog: pytest.LogCaptureFixture,
        run_glob: SearchRunner,
        run_grep: SearchRunner,
    ) -> None:
        write_tree(plain_dir, {"ok/a.txt": "needle\n"})
        tools = {"grep": (run_grep, "needle", grep_tool), "glob": (run_glob, "**/*.txt", glob_tool)}
        run, pattern, module = tools[tool]

        await run(plain_dir, pattern)

        [message] = warnings_from(caplog, _rg_runner)
        assert "exit code 2" in message
        assert "stands" in message
        assert "locked" in message
        assert warnings_from(caplog, module) == []

    async def test_glob_keeps_the_files_ripgrep_listed_before_it_failed(
        self, plain_dir: Path, monkeypatch: pytest.MonkeyPatch, run_glob: SearchRunner
    ) -> None:
        async def lists_one_then_fails(
            _cmd: Sequence[str], *, on_line: Callable[[bytes], bool], **_kwargs: object
        ) -> RgRunResult:
            on_line(b"listed.py\0")
            return RgRunResult(returncode=2, stderr="permission denied", stopped_early=False, lines_read=1)

        monkeypatch.setattr(glob_tool, "run_rg", lists_one_then_fails)
        write_tree(plain_dir, {"listed.py": "", "unlisted.py": ""})

        assert listed(await run_glob(plain_dir, "**/*.py")) == {"listed.py"}


@pytest.mark.usefixtures("ripgrep_fallback")
@pytest.mark.parametrize("engine", ["ripgrep"], indirect=True)
class TestRipgrepFailureFallsBack:
    """ripgrep gave no answer: the Python tier serves the call and one WARNING record names why."""

    async def test_pattern_ripgrep_cannot_parse_is_searched_by_the_python_tier(
        self, plain_dir: Path, caplog: pytest.LogCaptureFixture, run_grep: SearchRunner
    ) -> None:
        write_tree(plain_dir, {"a.py": "needle = 1\n", "b.py": "needle = 2\n"})

        output = await run_grep(plain_dir, r"needle(?= = 1)")

        assert hit_files(output, {"a.py", "b.py"}) == {"a.py"}
        [message] = warnings_from(caplog, grep_tool)
        assert "exit code 2" in message
        assert "look-around" in message

    async def test_grep_falls_back_when_ripgrep_times_out(
        self, plain_dir: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, run_grep: SearchRunner
    ) -> None:
        async def time_out(*_args: object, **_kwargs: object) -> None:
            raise TimeoutError

        monkeypatch.setattr(grep_tool, "run_rg", time_out)
        write_tree(plain_dir, {"a.py": "needle\n"})

        assert hit_files(await run_grep(plain_dir, "needle"), {"a.py"}) == {"a.py"}
        [message] = warnings_from(caplog, grep_tool)
        assert "TimeoutError" in message

    async def test_grep_falls_back_when_ripgrep_cannot_run(
        self, plain_dir: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, run_grep: SearchRunner
    ) -> None:
        async def cannot_run(*_args: object, **_kwargs: object) -> None:
            raise OSError("exec failed")

        monkeypatch.setattr(grep_tool, "run_rg", cannot_run)
        write_tree(plain_dir, {"a.py": "needle\n"})

        assert hit_files(await run_grep(plain_dir, "needle"), {"a.py"}) == {"a.py"}
        [message] = warnings_from(caplog, grep_tool)
        assert "OSError('exec failed')" in message

    async def test_glob_falls_back_when_ripgrep_cannot_run(
        self, plain_dir: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, run_glob: SearchRunner
    ) -> None:
        async def cannot_run(*_args: object, **_kwargs: object) -> None:
            raise OSError("exec failed")

        monkeypatch.setattr(glob_tool, "run_rg", cannot_run)
        write_tree(plain_dir, {"a.py": "needle\n"})

        assert listed(await run_glob(plain_dir, "**/*.py")) == {"a.py"}
        [message] = warnings_from(caplog, glob_tool)
        assert "OSError('exec failed')" in message

    async def test_glob_falls_back_when_ripgrep_fails_before_printing_anything(
        self, plain_dir: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, run_glob: SearchRunner
    ) -> None:
        async def fails(*_args: object, **_kwargs: object) -> RgRunResult:
            return RgRunResult(returncode=2, stderr="permission denied", stopped_early=False)

        monkeypatch.setattr(glob_tool, "run_rg", fails)
        write_tree(plain_dir, {"a.py": "needle\n"})

        assert listed(await run_glob(plain_dir, "**/*.py")) == {"a.py"}
        [message] = warnings_from(caplog, glob_tool)
        assert "exit code 2: permission denied" in message

    async def test_glob_falls_back_when_ripgrep_is_killed_after_printing_names(
        self, plain_dir: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, run_glob: SearchRunner
    ) -> None:
        async def killed_after_one_name(
            _cmd: Sequence[str], *, on_line: Callable[[bytes], bool], **_kwargs: object
        ) -> RgRunResult:
            on_line(b"unrelated.txt\0")
            return RgRunResult(returncode=-9, stderr="", stopped_early=False, lines_read=1)

        monkeypatch.setattr(glob_tool, "run_rg", killed_after_one_name)
        write_tree(plain_dir, {"a.py": "", "unrelated.txt": ""})

        # The one name it printed says nothing about the names it never reached.
        assert listed(await run_glob(plain_dir, "**/*.py")) == {"a.py"}
        [message] = warnings_from(caplog, glob_tool)
        assert "exit code -9" in message

    async def test_grep_falls_back_when_ripgrep_is_killed_after_printing(
        self, plain_dir: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, run_grep: SearchRunner
    ) -> None:
        async def killed_after_one_event(
            _cmd: Sequence[str], *, on_line: Callable[[bytes], bool], **_kwargs: object
        ) -> RgRunResult:
            on_line(b'{"type":"begin","data":{"path":{"text":"a.py"}}}\n')
            return RgRunResult(returncode=-9, stderr="", stopped_early=False, lines_read=1)

        monkeypatch.setattr(grep_tool, "run_rg", killed_after_one_event)
        write_tree(plain_dir, {"a.py": "needle\n", "b.py": "needle\n"})

        assert hit_files(await run_grep(plain_dir, "needle"), {"a.py", "b.py"}) == {"a.py", "b.py"}
        [message] = warnings_from(caplog, grep_tool)
        assert "exit code -9" in message
