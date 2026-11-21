"""Stand-in for the two subprocesses a shared venv needs, for the venv manager and executor tests.

``python -m venv --without-pip <path>`` makes ``<path>/bin/python`` (once ``release_creation`` is set when the test holds it back).
``<venv python> -m ensurepip ...`` makes ``<venv>/bin/pip`` once ``release`` is set, so a test decides how long the pip bootstrap
takes; when it fails it writes its message to the log file the manager gave it. Patch ``asyncio.create_subprocess_exec`` of the venv manager with an instance
(``patch(VENV_SPAWN, side_effect=FakeVenvSpawn())``).
"""

from __future__ import annotations

import asyncio
import io
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

VENV_SPAWN = "myrm_agent_harness.toolkits.code_execution.executors.common.venv_manager.asyncio.create_subprocess_exec"


@dataclass(frozen=True)
class Spawned:
    """One subprocess the venv manager started."""

    argv: tuple[str, ...]
    env: dict[str, str] | None
    cwd: str | None
    stdout: object
    stderr: object


class _FakeProcess:
    def __init__(
        self,
        venv_path: Path,
        *,
        creates: bool,
        exit_code: int,
        release: asyncio.Event,
        release_creation: asyncio.Event,
        log: io.BufferedIOBase | None = None,
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        self.returncode = exit_code
        self.pid = 0
        self._venv_path = venv_path
        self._creates = creates
        self._release = release
        self._release_creation = release_creation
        self._log = log
        self._on_cancel = on_cancel

    async def communicate(self) -> tuple[bytes, bytes]:
        if self._creates:
            await self._release_creation.wait()
            await asyncio.sleep(0.01)
            if self.returncode == 0:
                python = self._venv_path / "bin" / "python"
                python.parent.mkdir(parents=True, exist_ok=True)
                python.touch()
            return b"", b"venv failed" if self.returncode else b""
        try:
            await self._release.wait()
        except asyncio.CancelledError:
            if self._on_cancel is not None:
                self._on_cancel()
            raise
        if self.returncode == 0:
            (self._venv_path / "bin" / "pip").touch()
        elif self._log is not None:
            self._log.write(b"ensurepip failed")
            self._log.flush()
        return b"", b""


class FakeVenvSpawn:
    """``asyncio.create_subprocess_exec`` as the venv manager calls it."""

    def __init__(
        self,
        *,
        create_exit: int = 0,
        bootstrap_exit: int = 0,
        hold_bootstrap: bool = False,
        hold_creation: bool = False,
        bootstrap_error: OSError | None = None,
    ) -> None:
        self.calls: list[Spawned] = []
        self.cancelled_bootstraps = 0
        self.release = asyncio.Event()
        if not hold_bootstrap:
            self.release.set()
        self.release_creation = asyncio.Event()
        if not hold_creation:
            self.release_creation.set()
        self._create_exit = create_exit
        self._bootstrap_exit = bootstrap_exit
        self._bootstrap_error = bootstrap_error

    @property
    def creations(self) -> list[Spawned]:
        return [call for call in self.calls if "ensurepip" not in call.argv]

    @property
    def bootstraps(self) -> list[Spawned]:
        return [call for call in self.calls if "ensurepip" in call.argv]

    def __call__(self, *argv: str, **kwargs: object) -> _FakeProcess:
        """Synchronous on purpose: the ``AsyncMock`` that ``patch`` builds awaits the call for the code under test."""
        env, cwd, stdout, stderr = kwargs.get("env"), kwargs.get("cwd"), kwargs.get("stdout"), kwargs.get("stderr")
        self.calls.append(
            Spawned(argv, env if isinstance(env, dict) else None, cwd if isinstance(cwd, str) else None, stdout, stderr)
        )
        if "ensurepip" in argv:
            if self._bootstrap_error is not None:
                raise self._bootstrap_error
            return _FakeProcess(
                Path(argv[0]).parent.parent,
                creates=False,
                exit_code=self._bootstrap_exit,
                release=self.release,
                release_creation=self.release_creation,
                log=stderr if isinstance(stderr, io.BufferedIOBase) else None,
                on_cancel=self._count_cancelled_bootstrap,
            )
        return _FakeProcess(
            Path(argv[-1]),
            creates=True,
            exit_code=self._create_exit,
            release=self.release,
            release_creation=self.release_creation,
        )

    def _count_cancelled_bootstrap(self) -> None:
        self.cancelled_bootstraps += 1
