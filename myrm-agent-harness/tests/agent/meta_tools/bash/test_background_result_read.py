"""A background job's result that reaches the model through a tool call is reported as read.

The host queues a wake turn when a job finishes; when the model already holds the result, that turn only repeats it. So
every path that hands a finished job's own exit and output to the model tells the wakeup handler, and nothing else does:
a listing, a poll of a job that still runs, a wait that gave up, a stop and a wait that was cancelled report nothing.
"""

from __future__ import annotations

import asyncio
from collections.abc import Collection, Iterator
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.meta_tools.bash._background.registry import get_background_registry
from myrm_agent_harness.agent.meta_tools.bash.bash_process_tools import create_bash_process_tool
from myrm_agent_harness.toolkits.code_execution.executors.models import AsyncProcessProtocol
from myrm_agent_harness.utils.runtime.wakeup_registry import set_global_wakeup_handler
from tests.agent.meta_tools.bash.fake_background_proc import FakeOutputPipe, FakeProc, wait_until
from tests.agent.meta_tools.bash.real_stack import SESSION_ID, RealBashStack

if TYPE_CHECKING:
    from myrm_agent_harness.agent.sub_agents.types import SubAgentResult

_SESSION = "read-report-session"
_CONFIG: RunnableConfig = {"configurable": {"context": {"session_id": _SESSION}}}
_KILL_TARGET = "myrm_agent_harness.agent.meta_tools.bash._background.termination.kill_spawned_group"

# Every test starts from an empty registry and leaves no reader task behind.
pytestmark = pytest.mark.usefixtures("jobs")


class _ReadLedger:
    """The wakeup handler a host registers: it records which results the agent read, and in which session."""

    def __init__(self) -> None:
        self.reads: list[tuple[frozenset[str], str | None]] = []

    async def on_async_wakeup(self, result: SubAgentResult, agent_id: str, session_id: str | None) -> None:
        raise AssertionError("a background job never goes through the subagent wakeup")

    def on_results_read(self, task_ids: Collection[str], session_id: str | None) -> None:
        self.reads.append((frozenset(task_ids), session_id))


@pytest.fixture
def ledger() -> Iterator[_ReadLedger]:
    handler = _ReadLedger()
    set_global_wakeup_handler(handler)
    yield handler
    set_global_wakeup_handler(None)


async def _start_job(jobs: list[FakeProc], pid: int, *, running: bool = False) -> FakeProc:
    """A job of the test session: still running when *running*, else already exited with its two lines printed."""
    if running:
        proc = FakeProc(pid=pid, stdout=[], stdout_pipe=FakeOutputPipe([b"line-1\n"], hold_open=True))
    else:
        proc = FakeProc(pid=pid, stdout=[b"line-1\n", b"line-2\n"])
    jobs.append(proc)
    await get_background_registry().register(cast(AsyncProcessProtocol, proc), command="generate", session_id=_SESSION)
    if not running:
        proc.finish(0)
        await wait_until(lambda: _status(pid) == "exited", what="the job to exit")
    return proc


def _status(pid: int) -> str | None:
    info = get_background_registry().get(pid)
    return None if info is None else info.status


def _job_id(pid: int) -> str:
    info = get_background_registry().get(pid)
    assert info is not None
    return info.job_id


@pytest.mark.asyncio
async def test_output_of_a_finished_job_reports_the_result_read(jobs: list[FakeProc], ledger: _ReadLedger) -> None:
    await _start_job(jobs, 72001)

    await create_bash_process_tool().ainvoke({"action": "output", "pid": 72001}, config=_CONFIG)

    assert ledger.reads == [(frozenset({_job_id(72001)}), _SESSION)]


@pytest.mark.asyncio
async def test_output_of_a_running_job_reports_nothing(jobs: list[FakeProc], ledger: _ReadLedger) -> None:
    await _start_job(jobs, 72002, running=True)

    await create_bash_process_tool().ainvoke({"action": "output", "pid": 72002}, config=_CONFIG)

    assert ledger.reads == []


@pytest.mark.asyncio
async def test_wait_that_returns_the_exit_reports_the_result_read(jobs: list[FakeProc], ledger: _ReadLedger) -> None:
    proc = await _start_job(jobs, 72003, running=True)
    waiting = asyncio.create_task(
        create_bash_process_tool().ainvoke({"action": "wait", "pid": 72003, "timeout_seconds": 10}, config=_CONFIG)
    )
    await asyncio.sleep(0.05)
    assert ledger.reads == [], "a wait that still blocks has delivered nothing"

    proc.finish(0)
    result = await waiting

    assert result["metadata"]["still_running"] is False
    assert ledger.reads == [(frozenset({_job_id(72003)}), _SESSION)]


@pytest.mark.asyncio
async def test_wait_on_a_job_that_already_finished_reports_the_result_read(
    jobs: list[FakeProc], ledger: _ReadLedger
) -> None:
    await _start_job(jobs, 72004)

    await create_bash_process_tool().ainvoke({"action": "wait", "pid": 72004, "timeout_seconds": 10}, config=_CONFIG)

    assert ledger.reads == [(frozenset({_job_id(72004)}), _SESSION)]


@pytest.mark.asyncio
async def test_wait_that_gives_up_on_a_running_job_reports_nothing(jobs: list[FakeProc], ledger: _ReadLedger) -> None:
    await _start_job(jobs, 72005, running=True)

    result = await create_bash_process_tool().ainvoke(
        {"action": "wait", "pid": 72005, "timeout_seconds": 1}, config=_CONFIG
    )

    assert result["metadata"]["still_running"] is True
    assert ledger.reads == []


@pytest.mark.asyncio
async def test_a_cancelled_wait_reports_nothing(jobs: list[FakeProc], ledger: _ReadLedger) -> None:
    proc = await _start_job(jobs, 72006, running=True)
    waiting = asyncio.create_task(
        create_bash_process_tool().ainvoke({"action": "wait", "pid": 72006, "timeout_seconds": 30}, config=_CONFIG)
    )
    await asyncio.sleep(0.2)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting

    proc.finish(0)
    await wait_until(lambda: _status(72006) == "exited", what="the job to exit")

    assert ledger.reads == [], "the model never received the result of a wait that was cancelled"


@pytest.mark.asyncio
async def test_list_reports_nothing_even_for_a_finished_job(jobs: list[FakeProc], ledger: _ReadLedger) -> None:
    await _start_job(jobs, 72007)

    await create_bash_process_tool().ainvoke({"action": "list"}, config=_CONFIG)

    assert ledger.reads == []


@pytest.mark.asyncio
async def test_a_stopped_job_is_never_reported_read(jobs: list[FakeProc], ledger: _ReadLedger) -> None:
    """A stopped job is not settled by the host, so reading what it printed has nothing to stand down."""
    proc = await _start_job(jobs, 72008, running=True)
    tool = create_bash_process_tool()

    def _stop(_pid: int, sig: int) -> None:
        proc.finish(-sig)

    with patch(_KILL_TARGET, side_effect=_stop):
        await tool.ainvoke({"action": "kill", "pid": 72008}, config=_CONFIG)
    await wait_until(lambda: _status(72008) == "killed", what="the job to be marked killed")

    await tool.ainvoke({"action": "output", "pid": 72008}, config=_CONFIG)
    await tool.ainvoke({"action": "wait", "pid": 72008, "timeout_seconds": 5}, config=_CONFIG)

    assert ledger.reads == []


@pytest.mark.asyncio
async def test_a_job_of_another_session_reports_nothing(jobs: list[FakeProc], ledger: _ReadLedger) -> None:
    await _start_job(jobs, 72009)
    other: RunnableConfig = {"configurable": {"context": {"session_id": "another-session"}}}

    result = await create_bash_process_tool().ainvoke({"action": "output", "pid": 72009}, config=other)

    assert result["metadata"]["found"] is False
    assert ledger.reads == []


@pytest.mark.asyncio
async def test_a_handler_that_fails_does_not_fail_the_read(jobs: list[FakeProc]) -> None:
    class _Failing(_ReadLedger):
        def on_results_read(self, task_ids: Collection[str], session_id: str | None) -> None:
            raise RuntimeError("the host is down")

    await _start_job(jobs, 72010)
    set_global_wakeup_handler(_Failing())
    try:
        result = await create_bash_process_tool().ainvoke({"action": "output", "pid": 72010}, config=_CONFIG)
    finally:
        set_global_wakeup_handler(None)

    assert result["content"]["exit_code"] == 0
    assert result["content"]["stdout"] == ["line-1", "line-2"]


@pytest.mark.asyncio
async def test_no_handler_means_nothing_to_tell(jobs: list[FakeProc]) -> None:
    await _start_job(jobs, 72011)

    result = await create_bash_process_tool().ainvoke({"action": "output", "pid": 72011}, config=_CONFIG)

    assert result["content"]["exit_code"] == 0


_PYTEST_NAMED = "python3 -c \"print('pytest finished')\""
_PYTEST_SLOW = "python3 -c \"import time; print('pytest started', flush=True); time.sleep(30)\""


@pytest.mark.asyncio
async def test_a_command_that_ends_inside_the_auto_yield_window_reports_the_result_read(
    shared_real_stack: RealBashStack, ledger: _ReadLedger
) -> None:
    """The return of a build or test command that finished within the window carries its whole result."""
    returned = await shared_real_stack.run(_PYTEST_NAMED)

    assert "Command finished during auto-yield window" in returned
    assert "pytest finished" in returned
    (job,) = [
        j for j in get_background_registry().list_processes(session_id=SESSION_ID) if "pytest finished" in j.command
    ]
    assert ledger.reads == [(frozenset({job.job_id}), SESSION_ID)]


@pytest.mark.asyncio
async def test_a_command_that_becomes_a_background_job_reports_nothing_yet(
    shared_real_stack: RealBashStack, ledger: _ReadLedger
) -> None:
    """Its return says the command is still running, so the result is still to come."""
    content, pid = await shared_real_stack.run_detaching(_PYTEST_SLOW, yield_after_seconds=1)
    try:
        assert "detached as background job" in content
        assert ledger.reads == []
    finally:
        await shared_real_stack.stop_job(pid)
