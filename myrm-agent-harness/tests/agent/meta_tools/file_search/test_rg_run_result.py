"""Tests for ``RgRunResult.answered`` and what the runner reports about a finished ripgrep run.

Covers:
- A run that matched, found nothing or was stopped by us answers; status 2 answers only after some output
- Any other failure gives no answer: a flag ripgrep rejects, a crash status, a missing status
- ``require_answer`` raises for a run without an answer, naming its exit code and what it wrote to stderr
- A real child killed by a signal after it printed gave no answer, whatever it printed
- A failure that still answered is logged once by the runner, a failure without an answer is left to the caller
- Only the head of stderr is kept, however much ripgrep wrote
"""

from __future__ import annotations

import signal
import sys
from pathlib import Path

import pytest

from myrm_agent_harness.agent.meta_tools.file_search import _rg_runner
from myrm_agent_harness.agent.meta_tools.file_search._rg_runner import _STDERR_KEEP_CHARS, RgRunResult, run_rg
from tests.agent.meta_tools.file_search.search_probe import warnings_from


@pytest.mark.parametrize(
    ("returncode", "lines_read", "stopped_early", "answered"),
    [
        (0, 0, False, True),
        (1, 0, False, True),
        (2, 4, False, True),
        (2, 0, False, False),
        (127, 4, False, False),
        (-9, 4, False, False),
        (None, 4, False, False),
        (-9, 4, True, True),
    ],
)
def test_a_failed_run_answers_only_with_status_2_after_output(
    returncode: int | None, lines_read: int, stopped_early: bool, answered: bool
) -> None:
    """Status 2 after output is ripgrep searching on past an unreadable entry; a kill or a crash is not that."""
    result = RgRunResult(returncode=returncode, stderr="", stopped_early=stopped_early, lines_read=lines_read)

    assert result.answered is answered


def test_require_answer_names_the_exit_code_and_the_stderr_of_a_run_without_one() -> None:
    result = RgRunResult(returncode=2, stderr="regex parse error", stopped_early=False)

    with pytest.raises(RuntimeError, match="exit code 2: regex parse error"):
        result.require_answer()


def test_require_answer_accepts_a_run_that_answered() -> None:
    RgRunResult(returncode=2, stderr="permission denied", stopped_early=False, lines_read=3).require_answer()


@pytest.mark.skipif(
    sys.platform == "win32", reason="a Windows process has no signal death: its status is what the killer passed"
)
async def test_a_run_killed_by_a_signal_after_printing_gave_no_answer(tmp_path: Path) -> None:
    script = "import os, signal\nprint('a', flush=True)\nos.kill(os.getpid(), signal.SIGKILL)\n"

    result = await run_rg(
        [sys.executable, "-c", script], cwd=tmp_path, timeout_seconds=10.0, on_line=lambda _line: False
    )

    assert (result.returncode, result.lines_read, result.answered) == (-signal.SIGKILL, 1, False)


@pytest.mark.parametrize(
    ("script", "logged"),
    [
        ("import sys\nprint('a')\nsys.stderr.write('denied')\nsys.exit(2)\n", True),
        ("import sys\nsys.stderr.write('bad pattern')\nsys.exit(2)\n", False),
        ("print('a')\n", False),
    ],
    ids=["failed-after-output", "failed-without-output", "succeeded"],
)
async def test_only_a_failure_that_answered_is_logged_by_the_runner(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, script: str, logged: bool
) -> None:
    await run_rg([sys.executable, "-c", script], cwd=tmp_path, timeout_seconds=10.0, on_line=lambda _line: False)

    messages = warnings_from(caplog, _rg_runner)

    assert len(messages) == (1 if logged else 0)
    assert all("exit code 2" in message and "denied" in message for message in messages)


async def test_only_the_head_of_stderr_is_kept(tmp_path: Path) -> None:
    script = "import sys\nsys.stderr.write('head ' + 'x' * 1_000_000)\nsys.exit(2)\n"

    result = await run_rg(
        [sys.executable, "-c", script], cwd=tmp_path, timeout_seconds=10.0, on_line=lambda _line: False
    )

    assert result.returncode == 2
    assert len(result.stderr) == _STDERR_KEEP_CHARS
    assert result.stderr.startswith("head x")
