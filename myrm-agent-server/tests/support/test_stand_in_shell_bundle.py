"""A stand-in shell and its servers leave with the process they belong to.

A test run that is killed mid-test never reaches the smoke's own cleanup; without this, the stand-in's endless loop and
its two servers outlive the run and keep their ports.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path

import psutil
import pytest

from tests.support.stand_in_shell_bundle import stand_in_bundle

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the stand-in is a POSIX script")

# The shell looks for its owner every 0.2 s and the servers every 0.5 s; the margin is for a host too loaded to run them.
_EXIT_DEADLINE_SEC = 15.0
_START_DEADLINE_SEC = 30.0


@dataclass
class _EphemeralPorts:
    """Port 0 lets the kernel pick: these tests watch the processes and never connect to the servers."""

    backend: int = 0
    frontend: int = 0


@dataclass
class _Running:
    owner: subprocess.Popen[bytes]
    shell: subprocess.Popen[bytes]
    servers: list[int]


def _wait_for_servers(shell: subprocess.Popen[bytes]) -> list[int]:
    deadline = time.monotonic() + _START_DEADLINE_SEC
    while time.monotonic() < deadline:
        pids: list[int] = [child.pid for child in psutil.Process(shell.pid).children()]
        if len(pids) == 2:
            return pids
        time.sleep(0.1)
    pytest.fail("the stand-in shell did not start both of its servers")


def _existing(pids: list[int]) -> list[int]:
    return [pid for pid in pids if psutil.pid_exists(pid)]


def _survivors(pids: list[int]) -> list[int]:
    """The pids that still exist once the deadline has passed."""
    deadline = time.monotonic() + _EXIT_DEADLINE_SEC
    alive = _existing(pids)
    while alive and time.monotonic() < deadline:
        time.sleep(0.1)
        alive = _existing(pids)
    return alive


@contextmanager
def _stand_in(tmp_path: Path, behaviour: str) -> Iterator[_Running]:
    """A stand-in whose owner is a separate process the test can kill; whatever a failing test leaves is killed."""
    owner = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
    bundle = stand_in_bundle(tmp_path, _EphemeralPorts(), behaviour=behaviour, owner_pid=owner.pid)
    shell = subprocess.Popen(
        [str(bundle / "AppRun")],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        yield _Running(owner, shell, _wait_for_servers(shell))
    finally:
        with suppress(ProcessLookupError):
            os.killpg(shell.pid, signal.SIGKILL)
        shell.wait()
        owner.kill()
        owner.wait()


def _kill_owner(running: _Running) -> None:
    running.owner.kill()
    running.owner.wait()


def test_the_shell_and_its_servers_exit_once_their_owner_is_gone(tmp_path: Path) -> None:
    with _stand_in(tmp_path, "healthy") as running:
        _kill_owner(running)

        assert running.shell.wait(timeout=_EXIT_DEADLINE_SEC) == 0
        assert _survivors(running.servers) == []


def test_servers_a_leaky_shell_left_running_exit_with_the_owner(tmp_path: Path) -> None:
    with _stand_in(tmp_path, "leaky") as running:
        running.shell.send_signal(signal.SIGTERM)
        assert running.shell.wait(timeout=_EXIT_DEADLINE_SEC) == 0
        # The leak is what the smoke has to find, so the servers must outlive the shell while the owner lives.
        assert _existing(running.servers) == running.servers

        _kill_owner(running)

        assert _survivors(running.servers) == []
