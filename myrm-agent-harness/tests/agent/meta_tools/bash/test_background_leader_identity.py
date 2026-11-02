"""A job's group id is signalled only while it still belongs to the job, never because a stranger now holds the pid."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Callable, Iterator
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import psutil
import pytest

from myrm_agent_harness.agent.meta_tools.bash._background.registry import BackgroundProcessRegistry
from myrm_agent_harness.agent.meta_tools.bash._background.termination import (
    GroupMember,
    leader_id_reassigned,
    leader_identity,
    live_members,
    snapshot_group_members,
)
from myrm_agent_harness.toolkits.code_execution.executors.models import AsyncProcessProtocol
from myrm_agent_harness.utils import process_start
from myrm_agent_harness.utils.os_compat import get_process_group_kwargs
from myrm_agent_harness.utils.process_start import start_stamp
from tests.support.marked_processes import kill_marked, process_alive, wait_until

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="job groups are named after the leader pid on POSIX only"
)

_BACKGROUND = "myrm_agent_harness.agent.meta_tools.bash._background"
# Every sleeper below carries this prefix so teardown removes whatever a failing test left behind. The digits
# are the worker's pid, so parallel test workers never stop each other's sleepers; ``sleep`` accepts digits only.
_SLEEPER_PREFIX = f"sleep 4741.{os.getpid():07d}"
# Shifts a start stamp far beyond clock rounding: the holder of the pid then started long after the recorded leader.
_FAR_APART_SECONDS = 3600.0
_CLOCK_STEP_SECONDS = 120.0
# Instance attribute that holds the start time a process object first reported (see ``step_the_clock``).
_FIRST_START_TIME = "_first_reported_start_time"


def _sleeper(number: int) -> str:
    return f"{_SLEEPER_PREFIX}{number:02d}"


@pytest.fixture(autouse=True)
def _fake_pids_have_no_process_group() -> None:
    """These tests run real processes, so the real group lookup applies."""


@pytest.fixture(autouse=True)
def _remove_sleepers() -> Iterator[None]:
    yield
    kill_marked(_SLEEPER_PREFIX)


@pytest.fixture
async def registry() -> AsyncIterator[BackgroundProcessRegistry]:
    yield BackgroundProcessRegistry()


@pytest.fixture
async def group_leader() -> AsyncIterator[asyncio.subprocess.Process]:
    """A live process that leads its own group, the job's own group or the holder of a leader's pid.

    Registered as a job's leader it is the job's group; registered with a different recorded identity it is what the
    registry sees when a stranger is handed the leader's pid. A real pid wrap is not reproducible in a test, so that
    state is built by recording the different identity (see ``_register_on_held_pid``).
    """
    proc = await asyncio.create_subprocess_exec(
        *_sleeper(1).split(),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        **get_process_group_kwargs(),
    )
    await wait_until(lambda: process_alive(_sleeper(1)))
    yield proc
    kill_marked(_SLEEPER_PREFIX)
    await proc.wait()


@pytest.fixture
def step_the_clock(monkeypatch: pytest.MonkeyPatch) -> Callable[[float], None]:
    """Start times as psutil reports them on Linux, the boot time plus ticks since boot; the callable steps the clock.

    A clock step moves every such start time, which a recorded identity has to survive. As in psutil, a process object
    keeps the start time it first reported, so only an object built after a step reports the stepped time. The patch
    gives the same behaviour on every platform.
    """
    real_create_time = psutil.Process.create_time
    real_boot_time = psutil.boot_time()
    boot_time = [real_boot_time]

    def create_time(self: psutil.Process) -> float:
        started = vars(self).get(_FIRST_START_TIME)
        if started is None:
            started = real_create_time(self) - real_boot_time + boot_time[0]
            vars(self)[_FIRST_START_TIME] = started
        return started

    monkeypatch.setattr(psutil, "boot_time", lambda: boot_time[0])
    monkeypatch.setattr(psutil.Process, "create_time", create_time)
    monkeypatch.setattr(process_start, "_START_TIMES_FOLLOW_WALL_CLOCK", True)

    def step(seconds: float) -> None:
        boot_time[0] += seconds

    return step


class _HeldPid:
    """A leader handle for the pid ``group_leader`` holds: no output, and its exit comes when ``release`` is set."""

    def __init__(self, pid: int) -> None:
        self._proc = SimpleNamespace(pid=pid)  # the registry reads ``_proc.pid``
        self.stdout = self._closed_stream()
        self.stderr = self._closed_stream()
        self.stdin = None
        self.release = asyncio.Event()

    @staticmethod
    def _closed_stream() -> asyncio.StreamReader:
        stream = asyncio.StreamReader()
        stream.feed_eof()
        return stream

    async def wait(self) -> int:
        await self.release.wait()
        return 0


async def _register_on_held_pid(
    registry: BackgroundProcessRegistry, pid: int, *, session_id: str, reassigned: bool
) -> _HeldPid:
    """Register a job on ``pid``; when ``reassigned``, its recorded leader is a process that started long before."""
    held = _HeldPid(pid)
    handle = cast(AsyncProcessProtocol, held)
    if not reassigned:
        await registry.register(handle, command="held pid", session_id=session_id)
        return held
    holder = leader_identity(pid)
    assert holder is not None
    recorded = GroupMember(pid=pid, start_stamp=holder.start_stamp - _FAR_APART_SECONDS)
    with patch(f"{_BACKGROUND}.registry.leader_identity", return_value=recorded):
        await registry.register(handle, command="held pid", session_id=session_id)
    return held


async def _register_shell_job(registry: BackgroundProcessRegistry, script: str, *, session_id: str) -> int:
    """Run ``script`` as a job leader in its own group and register it; return the leader pid."""
    proc = await asyncio.create_subprocess_exec(
        "sh",
        "-c",
        script,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **get_process_group_kwargs(),
    )
    handle = SimpleNamespace(_proc=proc, stdout=proc.stdout, stderr=proc.stderr, wait=proc.wait)
    await registry.register(cast(AsyncProcessProtocol, handle), command=script, session_id=session_id)
    return proc.pid


def _status(registry: BackgroundProcessRegistry, pid: int) -> str | None:
    info = registry.get(pid)
    return info.status if info is not None else None


def _pid_nobody_holds() -> int:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


def test_leader_identity_is_the_pid_with_its_start_stamp() -> None:
    identity = leader_identity(os.getpid())

    assert identity is not None
    assert identity.pid == os.getpid()
    assert abs(identity.start_stamp - start_stamp(psutil.Process())) <= 1.0


@pytest.mark.parametrize("pid", [-5, 0, 1])
def test_no_leader_is_read_at_a_pid_a_job_cannot_have(pid: int) -> None:
    assert leader_identity(pid) is None


def test_no_leader_is_read_at_a_pid_nobody_holds() -> None:
    assert leader_identity(_pid_nobody_holds()) is None


def test_the_id_stays_trusted_unless_another_process_is_proven_to_hold_it() -> None:
    me = leader_identity(os.getpid())
    assert me is not None

    assert leader_id_reassigned(None) is False
    assert leader_id_reassigned(me) is False
    # The same process reads back a start stamp off by clock rounding.
    assert leader_id_reassigned(GroupMember(pid=me.pid, start_stamp=me.start_stamp + 0.5)) is False
    # Nobody holds the pid: the job's group can still be alive under that id.
    assert leader_id_reassigned(GroupMember(pid=_pid_nobody_holds(), start_stamp=1.0)) is False


def test_the_id_is_reassigned_when_the_holder_started_at_another_time() -> None:
    me = leader_identity(os.getpid())
    assert me is not None

    assert leader_id_reassigned(GroupMember(pid=me.pid, start_stamp=me.start_stamp - _FAR_APART_SECONDS)) is True
    assert leader_id_reassigned(GroupMember(pid=me.pid, start_stamp=me.start_stamp + _FAR_APART_SECONDS)) is True


def test_a_clock_step_does_not_make_the_leader_look_reassigned(step_the_clock: Callable[[float], None]) -> None:
    me = leader_identity(os.getpid())
    assert me is not None

    step_the_clock(_CLOCK_STEP_SECONDS)

    assert leader_id_reassigned(me) is False
    # A holder that really started at another time is still told apart after the step.
    assert leader_id_reassigned(GroupMember(pid=me.pid, start_stamp=me.start_stamp - _FAR_APART_SECONDS)) is True


@pytest.mark.asyncio
async def test_a_clock_step_does_not_hide_the_members_of_a_group(
    group_leader: asyncio.subprocess.Process, step_the_clock: Callable[[float], None]
) -> None:
    members = snapshot_group_members(group_leader.pid)
    assert [member.pid for member in members] == [group_leader.pid]

    step_the_clock(_CLOCK_STEP_SECONDS)

    assert [member.pid for member in live_members(group_leader.pid, members)] == [group_leader.pid]


@pytest.mark.asyncio
async def test_a_running_job_is_stopped_after_a_clock_step(
    registry: BackgroundProcessRegistry, step_the_clock: Callable[[float], None]
) -> None:
    sleeper = _sleeper(4)
    pid = await _register_shell_job(registry, f"{sleeper} & wait", session_id="lead-step-kill")
    await wait_until(lambda: process_alive(sleeper))

    step_the_clock(_CLOCK_STEP_SECONDS)

    assert await registry.kill(pid, grace_seconds=1.0) is True
    await wait_until(lambda: not process_alive(sleeper))


@pytest.mark.asyncio
async def test_what_a_finished_job_left_running_is_stopped_after_a_clock_step(
    registry: BackgroundProcessRegistry,
    group_leader: asyncio.subprocess.Process,
    step_the_clock: Callable[[float], None],
) -> None:
    held = await _register_on_held_pid(registry, group_leader.pid, session_id="lead-step-leftover", reassigned=False)
    held.release.set()
    await wait_until(lambda: _status(registry, group_leader.pid) == "exited")

    step_the_clock(_CLOCK_STEP_SECONDS)

    info = registry.get(group_leader.pid)
    assert info is not None
    assert info.leftover_processes == 1
    assert await registry.kill(group_leader.pid, grace_seconds=1.0) is True
    await wait_until(lambda: not process_alive(_sleeper(1)))


@pytest.mark.asyncio
@pytest.mark.parametrize("force", [False, True])
async def test_kill_leaves_a_pid_that_another_process_holds_alone(
    registry: BackgroundProcessRegistry, group_leader: asyncio.subprocess.Process, force: bool
) -> None:
    await _register_on_held_pid(registry, group_leader.pid, session_id="lead-kill", reassigned=True)

    assert await registry.kill(group_leader.pid, force=force, grace_seconds=0.2) is True

    assert process_alive(_sleeper(1))
    assert _status(registry, group_leader.pid) == "killed"
    info = registry.get(group_leader.pid)
    assert info is not None
    assert info.leftover_processes == 0


@pytest.mark.asyncio
async def test_shutdown_leaves_a_pid_that_another_process_holds_alone(
    registry: BackgroundProcessRegistry, group_leader: asyncio.subprocess.Process
) -> None:
    await _register_on_held_pid(registry, group_leader.pid, session_id="lead-shutdown", reassigned=True)

    registry.shutdown()

    assert process_alive(_sleeper(1))


@pytest.mark.asyncio
async def test_shutdown_stops_a_running_job_and_its_children(registry: BackgroundProcessRegistry) -> None:
    sleeper = _sleeper(2)
    await _register_shell_job(registry, f"{sleeper} & wait", session_id="lead-shutdown-live")
    await wait_until(lambda: process_alive(sleeper))

    registry.shutdown()

    await wait_until(lambda: not process_alive(sleeper))


@pytest.mark.asyncio
@pytest.mark.parametrize(("reassigned", "expected_leftover"), [(False, 1), (True, 0)])
async def test_the_exit_record_adopts_a_group_only_while_it_is_still_the_jobs(
    registry: BackgroundProcessRegistry,
    group_leader: asyncio.subprocess.Process,
    reassigned: bool,
    expected_leftover: int,
) -> None:
    held = await _register_on_held_pid(registry, group_leader.pid, session_id="lead-record", reassigned=reassigned)

    held.release.set()
    await wait_until(lambda: _status(registry, group_leader.pid) == "exited")

    info = registry.get(group_leader.pid)
    assert info is not None
    assert info.leftover_processes == expected_leftover
    # What was adopted as a leftover is what a later stop signals; what was not adopted stays untouched.
    assert await registry.kill(group_leader.pid, grace_seconds=1.0) is True
    assert process_alive(_sleeper(1)) is reassigned


@pytest.mark.asyncio
async def test_stopping_a_finished_job_checks_its_recorded_leader(
    registry: BackgroundProcessRegistry, group_leader: asyncio.subprocess.Process
) -> None:
    held = await _register_on_held_pid(registry, group_leader.pid, session_id="lead-finished-stop", reassigned=False)
    held.release.set()
    await wait_until(lambda: _status(registry, group_leader.pid) == "exited")

    # The pid counts as taken over only for a recorded leader: a stop that passes none would signal the group.
    with patch(f"{_BACKGROUND}.termination.leader_id_reassigned", side_effect=lambda leader: leader is not None):
        assert await registry.kill(group_leader.pid, grace_seconds=0.2) is True

    assert process_alive(_sleeper(1))


@pytest.mark.asyncio
async def test_a_job_whose_leader_exited_but_whose_children_run_is_still_stopped(
    registry: BackgroundProcessRegistry,
) -> None:
    sleeper = _sleeper(3)
    pid = await _register_shell_job(registry, f"{sleeper} & exit 0", session_id="lead-orphaned")
    await wait_until(lambda: not psutil.pid_exists(pid))
    await wait_until(lambda: process_alive(sleeper))
    # The sleeper inherited the pipes, so the registry still lists the job as running with its leader gone.
    assert _status(registry, pid) == "running"

    assert await registry.kill(pid, grace_seconds=1.0) is True

    assert not process_alive(sleeper)
