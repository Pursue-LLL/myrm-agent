"""Stopping a background job reaches everything it started, and says so when it cannot."""

from __future__ import annotations

import asyncio
import os
import shlex
import sys
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest

from myrm_agent_harness.agent.meta_tools.bash._background.registry import BackgroundProcessRegistry
from myrm_agent_harness.agent.meta_tools.bash._background.types import BackgroundProcessInfo, FinishListener
from myrm_agent_harness.agent.meta_tools.bash.bash_process_tools import create_bash_process_tool
from myrm_agent_harness.toolkits.code_execution.executors.models import AsyncProcessProtocol
from myrm_agent_harness.utils.os_compat import get_process_group_kwargs
from tests.support.marked_processes import kill_marked, process_alive, wait_until

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="job groups are named after the leader pid on POSIX only"
)

_BACKGROUND = "myrm_agent_harness.agent.meta_tools.bash._background"
_PROCESS_HANDLERS = "myrm_agent_harness.agent.meta_tools.bash._tool.process_handlers"
# Every sleeper below carries this prefix so teardown removes whatever a failing test left behind. The digits
# are the worker's pid, so parallel test workers never stop each other's sleepers; ``sleep`` accepts digits only.
_SLEEPER_PREFIX = f"sleep 4731.{os.getpid():07d}"


def _sleeper(number: int) -> str:
    return f"{_SLEEPER_PREFIX}{number:02d}"


@pytest.fixture(autouse=True)
def _fake_pids_have_no_process_group() -> None:
    """These tests run real processes, so the real group lookup applies."""


@pytest.fixture(autouse=True)
def _remove_sleepers() -> Iterator[None]:
    yield
    kill_marked(_SLEEPER_PREFIX)


class _RealProc:
    """A real child behind the handle shape the registry expects (it reads ``_proc.pid``)."""

    def __init__(self, proc: asyncio.subprocess.Process) -> None:
        self._proc = proc
        self.stdout = proc.stdout
        self.stderr = proc.stderr
        self.stdin = proc.stdin

    @property
    def pid(self) -> int:
        return self._proc.pid

    async def wait(self) -> int:
        return await self._proc.wait()


async def _spawn(
    registry: BackgroundProcessRegistry,
    script: str,
    *,
    session_id: str,
    finish_listener: FinishListener | None = None,
) -> int:
    proc = await asyncio.create_subprocess_exec(
        "sh",
        "-c",
        script,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **get_process_group_kwargs(),
    )
    real = _RealProc(proc)
    await registry.register(
        cast(AsyncProcessProtocol, real), command=script, session_id=session_id, finish_listener=finish_listener
    )
    # Another task can only stop the job after the reader has had its first turn; a stop issued before that would
    # cancel a reader that never ran and skip the finish listener.
    await asyncio.sleep(0)
    return real.pid


def _status(registry: BackgroundProcessRegistry, pid: int) -> str | None:
    info = registry.get(pid)
    return info.status if info is not None else None


def _leftover(registry: BackgroundProcessRegistry, pid: int) -> int:
    info = registry.get(pid)
    assert info is not None
    return info.leftover_processes


async def _spawn_job_that_leaves_a_sleeper(registry: BackgroundProcessRegistry, sleeper: str, session_id: str) -> int:
    """A job that exits at once after detaching a sleeper with closed pipes; return the job pid."""
    pid = await _spawn(registry, f"{sleeper} >/dev/null 2>&1 & exit 0", session_id=session_id)
    await wait_until(lambda: _status(registry, pid) == "exited")
    await wait_until(lambda: process_alive(sleeper))
    return pid


@pytest.fixture
async def registry() -> AsyncIterator[BackgroundProcessRegistry]:
    yield BackgroundProcessRegistry()


@pytest.mark.asyncio
async def test_a_finished_job_reports_what_it_left_running_and_kill_stops_it(
    registry: BackgroundProcessRegistry,
) -> None:
    sleeper = _sleeper(1)
    pid = await _spawn_job_that_leaves_a_sleeper(registry, sleeper, "term-left")

    info = registry.get(pid)
    assert info is not None
    assert info.leftover_processes == 1
    assert info.to_dict()["leftover_processes"] == 1

    assert await registry.kill(pid) is True

    assert _leftover(registry, pid) == 0
    assert not process_alive(sleeper)
    after = registry.get(pid)
    assert after is not None
    assert "leftover_processes" not in after.to_dict()


@pytest.mark.asyncio
async def test_killing_a_running_job_stops_its_background_children(registry: BackgroundProcessRegistry) -> None:
    sleeper = _sleeper(2)
    pid = await _spawn(registry, f"{sleeper} & wait", session_id="term-run")
    await wait_until(lambda: process_alive(sleeper))

    assert await registry.kill(pid) is True

    assert _status(registry, pid) == "killed"
    assert _leftover(registry, pid) == 0
    assert not process_alive(sleeper)


@pytest.mark.asyncio
@pytest.mark.parametrize("force", [True, False])
async def test_a_stopped_job_reaches_the_finish_listener_as_killed(
    registry: BackgroundProcessRegistry, force: bool
) -> None:
    """The reader must not get to report a job the caller stopped as an ordinary exit."""
    seen: list[str] = []

    async def on_finish(info: BackgroundProcessInfo) -> None:
        seen.append(info.status)

    sleeper = _sleeper(11)
    pid = await _spawn(registry, f"{sleeper} & wait", session_id="term-listener", finish_listener=on_finish)
    await wait_until(lambda: process_alive(sleeper))

    assert await registry.kill(pid, force=force) is True

    await wait_until(lambda: bool(seen))
    assert seen == ["killed"]


@pytest.mark.asyncio
async def test_a_job_that_ignores_sigterm_is_force_stopped_with_its_children(
    registry: BackgroundProcessRegistry,
) -> None:
    sleeper = _sleeper(3)
    pid = await _spawn(registry, f"trap '' TERM; {sleeper} & wait", session_id="term-ignore")
    await wait_until(lambda: process_alive(sleeper))

    assert await registry.kill(pid, grace_seconds=0.3) is True

    assert _leftover(registry, pid) == 0
    assert not process_alive(sleeper)


@pytest.mark.asyncio
async def test_a_stop_that_does_not_reach_the_children_leaves_them_reported(
    registry: BackgroundProcessRegistry,
) -> None:
    sleeper = _sleeper(4)
    pid = await _spawn_job_that_leaves_a_sleeper(registry, sleeper, "term-survivor")

    with patch(f"{_BACKGROUND}.termination.kill_spawned_group"):
        assert await registry.kill(pid, grace_seconds=0.1) is True

    assert _leftover(registry, pid) == 1
    assert process_alive(sleeper)


@pytest.mark.asyncio
async def test_a_finished_entry_stays_listed_while_its_children_run() -> None:
    registry = BackgroundProcessRegistry(reap_delay_seconds=0.1)
    sleeper = _sleeper(5)
    pid = await _spawn_job_that_leaves_a_sleeper(registry, sleeper, "term-reap")

    await asyncio.sleep(0.5)
    assert registry.get(pid) is not None

    kill_marked(sleeper)
    await wait_until(lambda: registry.get(pid) is None, timeout=5.0)


@pytest.mark.asyncio
async def test_the_kill_tool_reports_a_finished_job_whose_children_are_now_stopped(
    registry: BackgroundProcessRegistry,
) -> None:
    sleeper = _sleeper(6)
    pid = await _spawn_job_that_leaves_a_sleeper(registry, sleeper, "term-tool")
    tool = create_bash_process_tool()
    config = {"configurable": {"context": {"session_id": "term-tool"}}}
    with patch(f"{_PROCESS_HANDLERS}.get_background_registry", return_value=registry):
        result = await tool.ainvoke({"action": "kill", "pid": pid}, config=config)

    assert result["metadata"]["leftover_processes"] == 0
    assert "stopped the 1 process(es) it left running" in str(result["content"])
    assert not process_alive(sleeper)


@pytest.mark.asyncio
async def test_output_names_what_a_finished_job_left_running_until_it_is_stopped(
    registry: BackgroundProcessRegistry,
) -> None:
    sleeper = _sleeper(7)
    pid = await _spawn_job_that_leaves_a_sleeper(registry, sleeper, "term-output")
    tool = create_bash_process_tool()
    config = {"configurable": {"context": {"session_id": "term-output"}}}
    with patch(f"{_PROCESS_HANDLERS}.get_background_registry", return_value=registry):
        before = await tool.ainvoke({"action": "output", "pid": pid}, config=config)
        await tool.ainvoke({"action": "kill", "pid": pid}, config=config)
        after = await tool.ainvoke({"action": "output", "pid": pid}, config=config)

    assert before["content"]["status"] == "exited"
    assert before["content"]["leftover_processes"] == 1
    assert "leftover_processes" not in after["content"]


@pytest.mark.asyncio
async def test_wait_names_what_a_job_left_running_when_it_finishes_during_the_wait(
    registry: BackgroundProcessRegistry,
) -> None:
    sleeper = _sleeper(8)
    # The job is still running when the wait starts, so a count read before the wait would be zero.
    pid = await _spawn(registry, f"sleep 0.4; {sleeper} >/dev/null 2>&1 & exit 0", session_id="term-wait")
    tool = create_bash_process_tool()
    config = {"configurable": {"context": {"session_id": "term-wait"}}}
    with patch(f"{_PROCESS_HANDLERS}.get_background_registry", return_value=registry):
        result = await tool.ainvoke({"action": "wait", "pid": pid, "timeout_seconds": 10}, config=config)

    assert result["content"]["still_running"] is False
    assert result["content"]["leftover_processes"] == 1
    assert process_alive(sleeper)


@pytest.mark.asyncio
async def test_the_kill_tool_claims_nothing_where_the_platform_cannot_list_a_group(
    registry: BackgroundProcessRegistry,
) -> None:
    sleeper = _sleeper(27)
    pid = await _spawn(registry, f"{sleeper} & wait", session_id="term-blind")
    await wait_until(lambda: process_alive(sleeper))
    tool = create_bash_process_tool()
    config = {"configurable": {"context": {"session_id": "term-blind"}}}
    with (
        patch(f"{_PROCESS_HANDLERS}.get_background_registry", return_value=registry),
        patch(f"{_PROCESS_HANDLERS}.GROUP_VISIBLE", False),
    ):
        result = await tool.ainvoke({"action": "kill", "pid": pid}, config=config)

    assert result["content"] == f"Sent SIGTERM to pid={pid}"


@pytest.mark.asyncio
async def test_a_process_that_joins_the_group_after_the_job_ended_is_reported_and_stopped(
    registry: BackgroundProcessRegistry,
) -> None:
    """A leftover that forks later is found too, as long as a recorded member is still in the group."""
    parent, late_child = _sleeper(20), _sleeper(21)
    # The parent forks a SIGTERM-proof child half a second after the leader is gone, then becomes a sleeper itself.
    helper = f"sh -c 'sleep 0.5; (trap \"\" TERM; exec {late_child}) & exec {parent}'"
    pid = await _spawn(registry, f"{helper} >/dev/null 2>&1 & exit 0", session_id="term-late")
    await wait_until(lambda: _status(registry, pid) == "exited")
    await wait_until(lambda: process_alive(late_child))

    assert _leftover(registry, pid) == 2

    assert await registry.kill(pid, grace_seconds=0.5) is True

    assert _leftover(registry, pid) == 0
    assert not process_alive(parent)
    assert not process_alive(late_child)


@pytest.mark.asyncio
async def test_a_process_forked_while_the_job_is_being_stopped_is_stopped_too(
    registry: BackgroundProcessRegistry, tmp_path: Path
) -> None:
    """A TERM handler that forks a SIGTERM-proof helper and exits must not leave the helper behind."""
    helper, ready = _sleeper(26), tmp_path / "ready"
    handler = f'(trap "" TERM; exec {helper} >/dev/null 2>&1) & exit 0'
    script = f"trap '{handler}' TERM; : > {shlex.quote(str(ready))}; while :; do sleep 0.05; done"
    pid = await _spawn(registry, script, session_id="term-fork")
    await wait_until(ready.exists)

    assert await registry.kill(pid, grace_seconds=1.0) is True

    assert _status(registry, pid) == "killed"
    assert _leftover(registry, pid) == 0
    assert not process_alive(helper)


@pytest.mark.asyncio
async def test_a_process_that_left_the_group_is_no_longer_counted_as_a_leftover(
    registry: BackgroundProcessRegistry,
) -> None:
    """Once a recorded member starts its own session it is out of the job's reach; it must not read as unstoppable."""
    escaped = _sleeper(22)
    code = "import os, sys, time; time.sleep(0.5); os.setsid(); os.execvp('sleep', ['sleep', sys.argv[1]])"
    helper = shlex.join([sys.executable, "-c", code, escaped.removeprefix("sleep ")])
    pid = await _spawn(registry, f"{helper} >/dev/null 2>&1 & exit 0", session_id="term-escape")
    await wait_until(lambda: _status(registry, pid) == "exited")

    await wait_until(lambda: process_alive(escaped) and _leftover(registry, pid) == 0)

    assert await registry.kill(pid) is True
    assert _leftover(registry, pid) == 0


@pytest.mark.asyncio
async def test_a_slow_leader_and_a_child_that_ignores_sigterm_share_one_grace_period(
    registry: BackgroundProcessRegistry,
) -> None:
    """The leader and the group draw on one grace period instead of getting one each."""
    stubborn = _sleeper(23)
    code = (
        "import signal, subprocess, sys, time\n"
        "def slow_exit(*_):\n"
        "    time.sleep(0.8)\n"
        "    sys.exit(0)\n"
        "signal.signal(signal.SIGTERM, slow_exit)\n"
        "subprocess.Popen(['sh', '-c', 'trap \"\" TERM; exec sleep \"$0\"', sys.argv[1]],\n"
        "                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
        "while True:\n"
        "    time.sleep(0.05)\n"
    )
    leader = shlex.join([sys.executable, "-c", code, stubborn.removeprefix("sleep ")])
    pid = await _spawn(registry, f"exec {leader}", session_id="term-budget")
    await wait_until(lambda: process_alive(stubborn))

    started = time.monotonic()
    assert await registry.kill(pid, grace_seconds=1.0) is True
    elapsed = time.monotonic() - started

    assert elapsed < 1.5, f"stop took {elapsed:.2f}s with a 1.0s grace period"
    assert _leftover(registry, pid) == 0
    assert not process_alive(stubborn)


@pytest.mark.asyncio
async def test_shutdown_stops_what_a_finished_job_left_running(registry: BackgroundProcessRegistry) -> None:
    sleeper = _sleeper(24)
    await _spawn_job_that_leaves_a_sleeper(registry, sleeper, "term-shutdown")

    registry.shutdown()

    await wait_until(lambda: not process_alive(sleeper))


@pytest.mark.asyncio
async def test_two_stops_at_once_leave_the_job_stopped(registry: BackgroundProcessRegistry) -> None:
    sleeper = _sleeper(25)
    pid = await _spawn(registry, f"{sleeper} & wait", session_id="term-twice")
    await wait_until(lambda: process_alive(sleeper))

    assert await asyncio.gather(registry.kill(pid), registry.kill(pid)) == [True, True]

    await wait_until(lambda: not process_alive(sleeper))
    assert _status(registry, pid) == "killed"
    assert _leftover(registry, pid) == 0
