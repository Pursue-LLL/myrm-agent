"""The group scan behind a stop, and the startup reap of job leaders whose server is gone."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from unittest.mock import patch

import psutil
import pytest

from myrm_agent_harness.agent.meta_tools.bash._background.job_store import BackgroundJobStore
from myrm_agent_harness.agent.meta_tools.bash._background.termination import (
    GroupMember,
    LedgerLeader,
    leader_identity,
    live_members,
    own_identity,
    reap_orphaned_groups,
    snapshot_group_members,
)
from tests.support.marked_processes import kill_marked

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="job groups are named after the leader pid on POSIX only"
)

# Every sleeper below carries this prefix so teardown removes whatever a failing test left behind. The digits
# are the worker's pid, so parallel test workers never stop each other's sleepers; ``sleep`` accepts digits only.
_SLEEPER_PREFIX = f"sleep 4732.{os.getpid():07d}"
_TERMINATION = "myrm_agent_harness.agent.meta_tools.bash._background.termination"
_REAP_WAIT_SECONDS = 3.0
# Shifts a start stamp far beyond clock rounding: the holder of the pid then started long after the recorded server.
_FAR_APART_SECONDS = 3600.0

SpawnLeader = Callable[..., tuple[subprocess.Popen[bytes], float]]


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
def spawn_leader() -> Iterator[SpawnLeader]:
    """Start a sleeper the way a job leader is started; return it with the start time the ledger would record."""
    children: list[subprocess.Popen[bytes]] = []

    def spawn(number: int, *, own_group: bool = True) -> tuple[subprocess.Popen[bytes], float]:
        child = subprocess.Popen(
            ["sleep", _sleeper(number).removeprefix("sleep ")],
            start_new_session=own_group,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        children.append(child)
        return child, time.time()

    yield spawn
    for child in children:
        child.kill()
        child.wait()


def _gone_server() -> GroupMember:
    """The identity of a server that has exited and been reaped, so nobody holds its pid."""
    server = subprocess.Popen(["sleep", "30"])
    identity = leader_identity(server.pid)
    assert identity is not None
    server.kill()
    server.wait()
    return identity


def _this_server() -> GroupMember:
    identity = own_identity()
    assert identity is not None
    return identity


def _wait_for_zombie(process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + _REAP_WAIT_SECONDS
    while psutil.Process(process.pid).status() != psutil.STATUS_ZOMBIE:
        assert time.monotonic() < deadline, "the process did not exit"
        time.sleep(0.02)


def test_startup_reap_stops_a_job_leader_whose_server_is_gone(spawn_leader: SpawnLeader) -> None:
    # The leader's parent is this test process, alive and not init: the reap decides on the server, not on the parent.
    child, started_at = spawn_leader(7)

    assert reap_orphaned_groups([LedgerLeader(child.pid, started_at, _gone_server())]) == 1

    assert child.wait(timeout=_REAP_WAIT_SECONDS) == -signal.SIGKILL


def test_startup_reap_treats_a_server_pid_held_by_a_newer_process_as_gone(spawn_leader: SpawnLeader) -> None:
    child, started_at = spawn_leader(13)
    this_server = _this_server()
    recorded = GroupMember(pid=this_server.pid, start_stamp=this_server.start_stamp - _FAR_APART_SECONDS)

    assert reap_orphaned_groups([LedgerLeader(child.pid, started_at, recorded)]) == 1

    assert child.wait(timeout=_REAP_WAIT_SECONDS) == -signal.SIGKILL


def test_startup_reap_treats_a_server_that_exited_unreaped_as_gone(spawn_leader: SpawnLeader) -> None:
    child, started_at = spawn_leader(14)
    server = subprocess.Popen(["sleep", "0.3"])
    try:
        identity = leader_identity(server.pid)
        assert identity is not None
        _wait_for_zombie(server)

        assert reap_orphaned_groups([LedgerLeader(child.pid, started_at, identity)]) == 1
    finally:
        server.wait()

    assert child.wait(timeout=_REAP_WAIT_SECONDS) == -signal.SIGKILL


def test_a_platform_that_cannot_list_a_group_lists_nothing_and_reaps_nothing(spawn_leader: SpawnLeader) -> None:
    child, started_at = spawn_leader(12)

    with patch(f"{_TERMINATION}.GROUP_VISIBLE", False):
        assert snapshot_group_members(child.pid) == ()
        assert reap_orphaned_groups([LedgerLeader(child.pid, started_at, _gone_server())]) == 0

    assert child.poll() is None


@pytest.mark.parametrize(
    ("label", "started_offset"),
    [("another process started at that pid", 3600.0), ("recorded start in the future", -3600.0)],
)
def test_startup_reap_leaves_a_process_that_is_not_the_recorded_leader(
    spawn_leader: SpawnLeader, label: str, started_offset: float
) -> None:
    child, started_at = spawn_leader(8)

    assert reap_orphaned_groups([LedgerLeader(child.pid, started_at - started_offset, _gone_server())]) == 0, label
    assert child.poll() is None


def test_startup_reap_leaves_a_process_that_leads_no_group_of_its_own(spawn_leader: SpawnLeader) -> None:
    child, started_at = spawn_leader(15, own_group=False)

    assert reap_orphaned_groups([LedgerLeader(child.pid, started_at, _gone_server())]) == 0
    assert child.poll() is None


def test_startup_reap_leaves_a_leader_that_exited_unreaped(spawn_leader: SpawnLeader) -> None:
    child, started_at = spawn_leader(16)
    child.terminate()
    _wait_for_zombie(child)

    assert reap_orphaned_groups([LedgerLeader(child.pid, started_at, _gone_server())]) == 0


def test_startup_reap_leaves_a_job_whose_server_is_still_alive(spawn_leader: SpawnLeader) -> None:
    child, started_at = spawn_leader(9)

    assert reap_orphaned_groups([LedgerLeader(child.pid, started_at, _this_server())]) == 0
    assert child.poll() is None


def test_startup_reap_leaves_a_job_recorded_without_a_server(spawn_leader: SpawnLeader) -> None:
    child, started_at = spawn_leader(10)

    assert reap_orphaned_groups([LedgerLeader(child.pid, started_at, None)]) == 0
    assert child.poll() is None


def test_startup_reap_leaves_a_job_whose_server_cannot_be_read(spawn_leader: SpawnLeader) -> None:
    child, started_at = spawn_leader(11)
    server = _gone_server()
    real_process = psutil.Process

    def deny_the_server(pid: int) -> psutil.Process:
        if pid == server.pid:
            raise psutil.AccessDenied(pid)
        return real_process(pid)

    with patch(f"{_TERMINATION}.psutil.Process", side_effect=deny_the_server):
        assert reap_orphaned_groups([LedgerLeader(child.pid, started_at, server)]) == 0

    assert child.poll() is None


@pytest.mark.parametrize("which", ["zero", "init", "this_process"])
def test_startup_reap_never_signals_init_or_this_process(which: str) -> None:
    # Resolved here, not in the parametrize list: a worker-specific pid would give each xdist worker different test ids.
    pid = {"zero": 0, "init": 1, "this_process": os.getpid()}[which]
    assert reap_orphaned_groups([LedgerLeader(pid, psutil.Process().create_time(), _gone_server())]) == 0


def test_a_restart_stops_the_leader_of_a_job_whose_recorded_server_is_gone(
    spawn_leader: SpawnLeader, tmp_path: Path
) -> None:
    child, started_at = spawn_leader(18)
    ledger = BackgroundJobStore(tmp_path / "jobs.db")
    ledger.insert_running(
        job_id="job-gone",
        pid=child.pid,
        session_id="chat",
        command="serve",
        started_at=started_at,
        owner=_gone_server(),
    )

    assert ledger.reconcile_running_jobs(frozenset()) == 1

    assert child.wait(timeout=_REAP_WAIT_SECONDS) == -signal.SIGKILL
    record = ledger.get_by_job_id("job-gone")
    assert record is not None
    assert record.status == "orphaned"


@pytest.mark.parametrize("server", ["running", "unrecorded"])
def test_a_restart_leaves_the_leader_of_a_job_whose_server_may_still_run(
    spawn_leader: SpawnLeader, tmp_path: Path, server: str
) -> None:
    child, started_at = spawn_leader(19)
    ledger = BackgroundJobStore(tmp_path / "jobs.db")
    ledger.insert_running(
        job_id="job-kept",
        pid=child.pid,
        session_id="chat",
        command="serve",
        started_at=started_at,
        owner=_this_server() if server == "running" else None,
    )

    ledger.reconcile_running_jobs(frozenset())

    assert child.poll() is None


def test_a_group_snapshot_leaves_out_a_member_that_exited_unreaped(spawn_leader: SpawnLeader) -> None:
    child, _ = spawn_leader(20)
    assert [member.pid for member in snapshot_group_members(child.pid)] == [child.pid]
    child.terminate()
    _wait_for_zombie(child)

    assert snapshot_group_members(child.pid) == ()


def test_a_group_snapshot_lists_the_live_members_and_rejects_a_reused_pid() -> None:
    child = subprocess.Popen(["sleep", _sleeper(17).removeprefix("sleep ")], start_new_session=True)
    try:
        members = snapshot_group_members(child.pid)
        assert [m.pid for m in members] == [child.pid]
        assert live_members(child.pid, members) == members
        assert live_members(child.pid, [GroupMember(pid=child.pid, start_stamp=members[0].start_stamp + 3600.0)]) == ()
        assert live_members(child.pid, ()) == ()
        assert snapshot_group_members(1) == ()
    finally:
        child.kill()
        child.wait()
    assert live_members(child.pid, members) == ()
