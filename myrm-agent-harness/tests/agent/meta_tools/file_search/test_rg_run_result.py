"""Tests for ``RgRunResult.answered``: whether a finished ripgrep run stands as an answer.

Covers:
- A run that matched, found nothing or was stopped by us answers; status 2 answers only after some output
- Any other failure gives no answer: a flag ripgrep rejects, a crash status, a missing status
- A real child killed by a signal after it printed gave no answer, whatever it printed
"""

from __future__ import annotations

import signal
import sys
from pathlib import Path

import pytest

from myrm_agent_harness.agent.meta_tools.file_search._rg_runner import RgRunResult, run_rg


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


@pytest.mark.skipif(
    sys.platform == "win32", reason="a Windows process has no signal death: its status is what the killer passed"
)
async def test_a_run_killed_by_a_signal_after_printing_gave_no_answer(tmp_path: Path) -> None:
    script = "import os, signal\nprint('a', flush=True)\nos.kill(os.getpid(), signal.SIGKILL)\n"

    result = await run_rg(
        [sys.executable, "-c", script], cwd=tmp_path, timeout_seconds=10.0, on_line=lambda _line: False
    )

    assert (result.returncode, result.lines_read, result.answered) == (-signal.SIGKILL, 1, False)
