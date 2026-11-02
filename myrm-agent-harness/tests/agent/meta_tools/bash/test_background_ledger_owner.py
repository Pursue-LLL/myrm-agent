"""A job's ledger row names the server that registered it, so a later start can tell whether that server is gone."""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import psutil
import pytest

from myrm_agent_harness.agent.meta_tools.bash._background.job_store import (
    BackgroundJobStore,
    configure_background_job_store,
    reset_background_job_store_for_tests,
)
from myrm_agent_harness.agent.meta_tools.bash._background.registry import BackgroundProcessRegistry
from myrm_agent_harness.agent.meta_tools.bash._background.termination import leader_identity, own_identity
from myrm_agent_harness.toolkits.code_execution.executors.models import AsyncProcessProtocol
from myrm_agent_harness.utils.os_compat import get_process_group_kwargs
from myrm_agent_harness.utils.process_start import start_stamp
from tests.support.marked_processes import kill_marked, process_alive, wait_until

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="job groups are named after the leader pid on POSIX only"
)

# Every sleeper below carries this prefix so teardown removes whatever a failing test left behind. The digits
# are the worker's pid, so parallel test workers never stop each other's sleepers; ``sleep`` accepts digits only.
_SLEEPER = f"sleep 4753.{os.getpid():09d}"
_REGISTRY_LOGGER = "myrm_agent_harness.agent.meta_tools.bash._background.registry"
# A stamp read twice for one process differs by clock rounding at most.
_STAMP_ROUNDING_SECONDS = 1.0


@pytest.fixture(autouse=True)
def _fake_pids_have_no_process_group() -> None:
    """These tests run real processes, so the real group lookup applies."""


@pytest.fixture(autouse=True)
def _remove_sleepers() -> Iterator[None]:
    yield
    kill_marked(_SLEEPER)


@pytest.fixture
def ledger(tmp_path: Path) -> Iterator[BackgroundJobStore]:
    reset_background_job_store_for_tests()
    yield configure_background_job_store(tmp_path / "jobs.db")
    reset_background_job_store_for_tests()


@pytest.fixture
async def registry() -> AsyncIterator[BackgroundProcessRegistry]:
    yield BackgroundProcessRegistry()


async def _register_sleeper(registry: BackgroundProcessRegistry, *, session_id: str) -> int:
    proc = await asyncio.create_subprocess_exec(
        *_SLEEPER.split(),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **get_process_group_kwargs(),
    )
    handle = SimpleNamespace(_proc=proc, stdout=proc.stdout, stderr=proc.stderr, wait=proc.wait)
    await registry.register(cast(AsyncProcessProtocol, handle), command=_SLEEPER, session_id=session_id)
    return proc.pid


def test_a_server_is_identified_by_its_pid_and_start_stamp() -> None:
    identity = own_identity()

    assert identity is not None
    assert identity.pid == os.getpid()
    assert abs(identity.start_stamp - start_stamp(psutil.Process())) <= _STAMP_ROUNDING_SECONDS
    assert identity == leader_identity(os.getpid())


def test_a_server_that_is_init_has_no_identity() -> None:
    # Init cannot be told apart from a stranger holding pid 1, so it is never recorded as an owner.
    with patch("os.getpid", return_value=1):
        assert own_identity() is None


@pytest.mark.asyncio
async def test_a_registered_job_records_this_server_as_its_owner(
    registry: BackgroundProcessRegistry, ledger: BackgroundJobStore
) -> None:
    pid = await _register_sleeper(registry, session_id="owner-record")
    await wait_until(lambda: process_alive(_SLEEPER))

    record = ledger.get_by_pid(pid)

    server = own_identity()
    assert server is not None
    assert record is not None
    assert record.owner_pid == server.pid
    assert record.owner_start_stamp is not None
    assert abs(record.owner_start_stamp - server.start_stamp) <= _STAMP_ROUNDING_SECONDS
    registry.shutdown()


@pytest.mark.asyncio
async def test_a_job_still_runs_when_the_ledger_cannot_record_it(
    registry: BackgroundProcessRegistry, ledger: BackgroundJobStore, caplog: pytest.LogCaptureFixture
) -> None:
    with (
        patch.object(ledger, "insert_running", side_effect=sqlite3.OperationalError("database is locked")),
        caplog.at_level(logging.WARNING, logger=_REGISTRY_LOGGER),
    ):
        pid = await _register_sleeper(registry, session_id="owner-unrecorded")

    await wait_until(lambda: process_alive(_SLEEPER))
    info = registry.get(pid)
    assert info is not None
    assert info.status == "running"
    assert "Background job store insert failed" in caplog.text
    registry.shutdown()
