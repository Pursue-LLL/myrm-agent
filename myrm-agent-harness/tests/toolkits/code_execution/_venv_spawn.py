"""Test kit for the shared venv: a stand-in for its ``python -m venv <path>`` subprocess, and the manager and loop helpers around it.

The stdlib command links the interpreter first (``bin/python``, ``python3`` and ``python3.N``, symlinks), then installs pip, which is most of its
time. The fake does the same on a schedule the test controls: the links appear once ``release_links`` is set (``python3`` and ``python3.N``
once ``release_aliases`` is set too), pip appears and the process ends once ``release_build`` is set; a failing build writes its message to the
log file the manager gave it. ``terminate()`` ends it at any point. Patch ``asyncio.create_subprocess_exec`` of the venv manager with an
instance (``patch(VENV_SPAWN, side_effect=FakeVenvSpawn())``).
"""

from __future__ import annotations

import asyncio
import io
import sys
from dataclasses import dataclass
from pathlib import Path

from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.common.venv_manager import VenvManager

VENV_SPAWN = "myrm_agent_harness.toolkits.code_execution.executors.common.venv_manager.asyncio.create_subprocess_exec"
ALIASES = ("python3", f"python3.{sys.version_info[1]}")
TERMINATED = -15


@dataclass(frozen=True)
class Spawned:
    """One subprocess the venv manager started."""

    argv: tuple[str, ...]
    stdout: object
    stderr: object


class _FakeVenvProcess:
    def __init__(self, venv_path: Path, spawn: FakeVenvSpawn, log: io.BufferedIOBase | None) -> None:
        self.returncode: int | None = None
        self.pid = 0
        self._venv_path = venv_path
        self._spawn = spawn
        self._log = log
        self._stopped = asyncio.Event()
        self._run_task = asyncio.get_running_loop().create_task(self._run())

    async def _released(self, event: asyncio.Event) -> bool:
        """Wait until ``event`` is set; False when the process was terminated first."""
        waits = [asyncio.ensure_future(event.wait()), asyncio.ensure_future(self._stopped.wait())]
        try:
            await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for wait in waits:
                wait.cancel()
        return not self._stopped.is_set()

    async def _run(self) -> None:
        spawn = self._spawn
        if not await self._released(spawn.release_links):
            self._end(TERMINATED, b"")
        elif spawn.dies_before_linking:
            self._end(1, b"venv failed")
        else:
            self._link("python")
            if await self._released(spawn.release_aliases):
                for alias in ALIASES:
                    self._link(alias)
            if await self._released(spawn.release_build):
                self._finish_build()
            else:
                self._end(TERMINATED, b"")

    def _finish_build(self) -> None:
        if self._spawn.build_exit == 0:
            (self._venv_path / "bin").mkdir(parents=True, exist_ok=True)
            (self._venv_path / "bin" / "pip").touch()
            self._end(0, b"")
        else:
            self._end(self._spawn.build_exit, b"ensurepip failed")

    def _link(self, name: str) -> None:
        path = self._venv_path / "bin" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if self._spawn.copies:
            path.touch()
        elif name == "python":
            path.symlink_to(sys.executable)
        else:
            path.symlink_to("python")

    def _end(self, exit_code: int, message: bytes) -> None:
        if message and self._log is not None:
            self._log.write(message)
            self._log.flush()
        self.returncode = exit_code

    async def communicate(self) -> tuple[bytes, bytes]:
        try:
            await asyncio.shield(self._run_task)
        except asyncio.CancelledError:
            self._spawn.abandoned += 1
            raise
        return b"", b""

    def terminate(self) -> None:
        self._spawn.terminated += 1
        self._stopped.set()

    def kill(self) -> None:
        self.terminate()

    async def wait(self) -> int | None:
        await asyncio.shield(self._run_task)
        return self.returncode


class FakeVenvSpawn:
    """``asyncio.create_subprocess_exec`` as the venv manager calls it."""

    def __init__(
        self,
        *,
        build_exit: int = 0,
        hold_links: bool = False,
        hold_aliases: bool = False,
        hold_build: bool = False,
        copies: bool = False,
        dies_before_linking: bool = False,
        spawn_error: OSError | None = None,
    ) -> None:
        self.calls: list[Spawned] = []
        self.abandoned = 0
        self.terminated = 0
        self.build_exit = build_exit
        self.copies = copies
        self.dies_before_linking = dies_before_linking
        self._spawn_error = spawn_error
        self.release_links, self.release_aliases, self.release_build = asyncio.Event(), asyncio.Event(), asyncio.Event()
        for held, event in (
            (hold_links, self.release_links),
            (hold_aliases, self.release_aliases),
            (hold_build, self.release_build),
        ):
            if not held:
                event.set()

    @property
    def creations(self) -> list[Spawned]:
        return self.calls

    def __call__(self, *argv: str, **kwargs: object) -> _FakeVenvProcess:
        """Synchronous on purpose: the ``AsyncMock`` that ``patch`` builds awaits the call for the code under test."""
        if argv[1:3] != ("-m", "venv") or not Path(argv[-1]).is_absolute():
            raise AssertionError(
                f"the venv manager started something other than `python -m venv <absolute path>`: {argv}"
            )
        stdout, stderr = kwargs.get("stdout"), kwargs.get("stderr")
        self.calls.append(Spawned(argv, stdout, stderr))
        if self._spawn_error is not None:
            raise self._spawn_error
        return _FakeVenvProcess(Path(argv[-1]), self, stderr if isinstance(stderr, io.BufferedIOBase) else None)


def make_manager(tmp_path: Path, *, auto_create: bool = True) -> VenvManager:
    """A manager whose shared venv lives at ``<tmp_path>/venvs``."""
    config = ExecutionConfig()
    config.local.shared_venv_path = str(tmp_path / "venvs")
    config.local.auto_create_venv = auto_create
    return VenvManager(config)


async def let_the_loop_run() -> None:
    """Give every task that can make progress the chance to do so."""
    await asyncio.sleep(0.05)
