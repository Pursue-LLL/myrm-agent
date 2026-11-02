"""A real restart through the server's startup hook: which job processes the ledger it opens makes it stop.

[INPUT]
- ``init_background_job_store`` (POS: the only caller of the ledger reconcile, run once when the server starts)
- A ledger file on disk and real processes standing in for job leaders and for the server that registered them

[OUTPUT]
- Fails when a restart leaves the leader of a job whose server is gone running, stops a leader whose server may still be
  running, or stops the startup when the ledger cannot be opened.

[POS]
The reconcile itself is covered in the harness; this checks the wiring of the hook to it, with the ledger at the path the hook
derives from the harness directory.
"""

from __future__ import annotations

import logging
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from myrm_agent_harness.agent.meta_tools.bash._background.job_store import (
    BackgroundJobStore,
    get_background_job_store,
    reset_background_job_store_for_tests,
)
from myrm_agent_harness.agent.meta_tools.bash._background.termination import GroupMember, leader_identity, own_identity

from app.services.agent.background_job.background_job_startup import init_background_job_store
from app.services.context.context_assembly import ContextAssemblyService

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="job groups are named after the leader pid on POSIX only")

_REAP_WAIT_SECONDS = 5.0


@pytest.fixture(autouse=True)
def _ledger_under_tmp(tmp_path: Path) -> Iterator[None]:
    """Point the hook at a ledger of this test; the process-wide store is bound by the hook, so it is cleared around the test."""
    reset_background_job_store_for_tests()
    facade = SimpleNamespace(harness_path=lambda: tmp_path)
    with patch.object(ContextAssemblyService, "build_facade", return_value=facade):
        yield
    reset_background_job_store_for_tests()


@pytest.fixture
def leader() -> Iterator[tuple[subprocess.Popen[bytes], float]]:
    """A job leader as the registry starts one: alone in its own session, with the start time the ledger would record."""
    child = subprocess.Popen(
        ["sleep", "300"],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    yield child, time.time()
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


def _running_server() -> GroupMember:
    identity = own_identity()
    assert identity is not None
    return identity


def _record_job(harness_dir: Path, leader: tuple[subprocess.Popen[bytes], float], owner: GroupMember | None) -> None:
    child, started_at = leader
    ledger = harness_dir / ".myrm" / "background_jobs.db"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    BackgroundJobStore(ledger).insert_running(
        job_id="job-1", pid=child.pid, session_id="chat", command="serve", started_at=started_at, owner=owner
    )


def test_a_restart_stops_the_leader_of_a_job_whose_recorded_server_is_gone(
    tmp_path: Path, leader: tuple[subprocess.Popen[bytes], float]
) -> None:
    _record_job(tmp_path, leader, _gone_server())

    init_background_job_store()

    assert leader[0].wait(timeout=_REAP_WAIT_SECONDS) == -signal.SIGKILL
    store = get_background_job_store()
    assert store is not None
    record = store.get_by_job_id("job-1")
    assert record is not None
    assert record.status == "orphaned"


@pytest.mark.parametrize("server", ["running", "unrecorded"])
def test_a_restart_leaves_the_leader_of_a_job_whose_server_may_still_run(
    tmp_path: Path, leader: tuple[subprocess.Popen[bytes], float], server: str
) -> None:
    _record_job(tmp_path, leader, _running_server() if server == "running" else None)

    init_background_job_store()

    assert leader[0].poll() is None


def test_startup_goes_on_when_the_ledger_cannot_be_opened(caplog: pytest.LogCaptureFixture) -> None:
    with (
        patch.object(ContextAssemblyService, "build_facade", side_effect=RuntimeError("no harness directory")),
        caplog.at_level(logging.WARNING),
    ):
        init_background_job_store()

    assert "BackgroundJobStore configuration skipped" in caplog.text


def test_startup_goes_on_when_no_ledger_is_available() -> None:
    with patch("myrm_agent_harness.api.hooks.get_background_job_store", return_value=None):
        init_background_job_store()
