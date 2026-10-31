"""A remote command that never ends or never stops printing cannot grow the server's memory or outlive its deadline.

[INPUT]
- pytest, asyncio, time, tracemalloc
- app.services.ssh_vault::SSHAssetService, SSHHostConfig
- tests.services.ssh_vault.conftest::StandInSsh (a program named `ssh` that never connects)

[OUTPUT]
- Tests of `execute_remote_command`: output and exit code come through, a flood stops at the timeout, output past the cap
  is cut with a note (alone when stderr is empty), a cancelled call stops the `ssh` process.

[POS]
Tests in tests/services/ssh_vault/. They run a real child process in place of `ssh`.
"""

from __future__ import annotations

import asyncio
import time
import tracemalloc
from typing import TYPE_CHECKING

import pytest

from app.services.ssh_vault.models import SSHHostConfig
from app.services.ssh_vault.service import SSHAssetService

if TYPE_CHECKING:
    from tests.services.ssh_vault.conftest import StandInSsh

_CAP = 5 * 1024 * 1024
_TIMEOUT_SECONDS = 2.0


def _service() -> SSHAssetService:
    service = SSHAssetService()
    service.register_host(SSHHostConfig(host_alias="exec-node", hostname="10.0.0.1", user="test", is_read_only=False))
    return service


@pytest.mark.parametrize("exit_code", [0, 3])
async def test_output_and_exit_code_come_through(stand_in_ssh: StandInSsh, exit_code: int) -> None:
    stand_in_ssh.print_and_exit(stdout="hello-remote", stderr="warn", exit_code=exit_code)

    result = await _service().execute_remote_command("exec-node", "echo hello-remote")

    assert (result.exit_code, result.stdout, result.stderr, result.is_timeout) == (exit_code, "hello-remote", "warn", False)
    assert stand_in_ssh.is_gone()


@pytest.mark.parametrize("pipe", ["stdout", "stderr"])
async def test_a_flood_ends_at_the_timeout_with_the_process_gone_and_memory_bounded(stand_in_ssh: StandInSsh, pipe: str) -> None:
    stand_in_ssh.flood(pipe)
    service = _service()

    tracemalloc.start()
    try:
        started = time.monotonic()
        result = await service.execute_remote_command("exec-node", "tail -f /var/log/syslog", timeout_seconds=_TIMEOUT_SECONDS)
        elapsed = time.monotonic() - started
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert result.is_timeout is True
    assert result.exit_code == 124
    assert elapsed < _TIMEOUT_SECONDS + 5
    assert stand_in_ssh.is_gone()
    # Held output may take up to 2 x cap (one pipe at the cap, one being read); an unbounded read of the flood
    # reaches that within a fraction of a second and keeps climbing for the rest of the timeout.
    assert peak < 3 * _CAP


async def test_output_past_the_cap_is_cut_with_a_note(stand_in_ssh: StandInSsh) -> None:
    stand_in_ssh.print_and_exit(stdout="x" * (_CAP + 4096), stderr="warn")

    result = await _service().execute_remote_command("exec-node", "cat /var/log/big.log")

    assert result.exit_code == 0
    assert len(result.stdout) == _CAP
    assert result.stderr.startswith("warn\n[Output limit reached: ")


async def test_output_past_the_cap_without_stderr_leaves_the_note_alone(stand_in_ssh: StandInSsh) -> None:
    stand_in_ssh.print_and_exit(stdout="x" * (_CAP + 4096))

    result = await _service().execute_remote_command("exec-node", "cat /var/log/big.log")

    assert len(result.stdout) == _CAP
    assert result.stderr.startswith("[Output limit reached: ")
    assert result.stderr.endswith("the rest was discarded]")


async def test_output_within_the_cap_has_no_note(stand_in_ssh: StandInSsh) -> None:
    stand_in_ssh.print_and_exit(stdout="x" * _CAP)

    result = await _service().execute_remote_command("exec-node", "cat /var/log/exact.log")

    assert len(result.stdout) == _CAP
    assert result.stderr == ""


async def test_a_cancelled_call_stops_the_ssh_process(stand_in_ssh: StandInSsh) -> None:
    stand_in_ssh.hold()
    call = asyncio.create_task(_service().execute_remote_command("exec-node", "sleep 100", timeout_seconds=60))
    while not stand_in_ssh.was_started():
        await asyncio.sleep(0.05)

    call.cancel()
    with pytest.raises(asyncio.CancelledError):
        await call

    assert stand_in_ssh.is_gone()
