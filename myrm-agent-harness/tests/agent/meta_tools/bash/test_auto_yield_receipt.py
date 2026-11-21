"""What the auto-yield receipt says about the lines it leaves out.

A build or test command that ends or outlives its yield window returns the last 50 lines of the job. A job that printed
more says so, and names the log that holds the whole output when it has one.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import cast

import pytest

from myrm_agent_harness.agent.meta_tools.bash._background.registry import get_background_registry
from myrm_agent_harness.agent.meta_tools.bash._background.types import BackgroundProcessInfo
from myrm_agent_harness.agent.meta_tools.bash._executor.auto_yield import build_auto_yield_return
from myrm_agent_harness.toolkits.code_execution.executors.models import AsyncProcessProtocol
from tests.agent.meta_tools.bash.fake_background_proc import FakeOutputPipe, FakeProc, wait_until

pytestmark = pytest.mark.usefixtures("jobs")

_SESSION = "receipt-session"


async def _job(jobs: list[FakeProc], pid: int, lines: int, *, finished: bool) -> BackgroundProcessInfo:
    """A job that printed ``line-1`` to ``line-<lines>``: ended when *finished*, otherwise alive and silent."""
    text = ("\n".join(f"line-{i}" for i in range(1, lines + 1)) + "\n").encode()
    proc = FakeProc(pid=pid, stdout=[], stdout_pipe=FakeOutputPipe([text], hold_open=not finished))
    jobs.append(proc)
    registry = get_background_registry()
    await registry.register(cast(AsyncProcessProtocol, proc), command="npm test", session_id=_SESSION)
    entry = registry._entries[pid]
    await wait_until(lambda: entry.stdout_total == lines, what="the lines to be read")
    if finished:
        proc.finish(0)
        assert entry.reader_task is not None
        await asyncio.wait_for(entry.reader_task, timeout=5)
    info = registry.get(pid)
    assert info is not None
    return info


def _receipt(info: BackgroundProcessInfo) -> str:
    return str(build_auto_yield_return(info=info, yield_seconds=5)["content"])


def _printed_lines(receipt: str) -> list[str]:
    return re.findall(r"^line-\d+$", receipt, re.MULTILINE)


@pytest.mark.asyncio
async def test_a_job_of_fifty_lines_is_shown_whole_without_a_note(jobs: list[FakeProc], workspace: Path) -> None:
    receipt = _receipt(await _job(jobs, 75001, 50, finished=True))

    assert _printed_lines(receipt) == [f"line-{i}" for i in range(1, 51)]
    assert "not shown" not in receipt


@pytest.mark.asyncio
async def test_a_finished_job_names_the_log_that_holds_the_lines_its_receipt_leaves_out(
    jobs: list[FakeProc], workspace: Path
) -> None:
    receipt = _receipt(await _job(jobs, 75002, 120, finished=True))

    assert _printed_lines(receipt) == [f"line-{i}" for i in range(71, 121)]
    named = re.search(r"\[Earlier 70 lines not shown\. Full output: (\S+) \(read it with file_read_tool\)\]", receipt)
    assert named is not None
    assert (workspace / named.group(1)).read_text(encoding="utf-8").splitlines() == [f"line-{i}" for i in range(1, 121)]


@pytest.mark.asyncio
async def test_a_running_job_says_so_in_the_partial_output(jobs: list[FakeProc], workspace: Path) -> None:
    receipt = _receipt(await _job(jobs, 75003, 120, finished=False))

    assert "still running" in receipt
    assert "Partial output:\n[Earlier 70 lines not shown. Full output: " in receipt


@pytest.mark.asyncio
async def test_without_a_log_the_receipt_still_says_lines_are_missing(jobs: list[FakeProc], workspace: Path) -> None:
    receipt = _receipt(await _job(jobs, 75004, 60, finished=True))

    assert "[Earlier 10 lines not shown.]" in receipt
    assert "Full output" not in receipt


@pytest.mark.asyncio
async def test_a_single_missing_line_is_not_called_lines(jobs: list[FakeProc], workspace: Path) -> None:
    receipt = _receipt(await _job(jobs, 75005, 51, finished=True))

    assert "[Earlier 1 line not shown.]" in receipt
