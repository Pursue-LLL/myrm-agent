"""Stand-in for the two subprocesses a shared venv needs, for the venv manager and executor tests.

``python -m venv --without-pip <path>`` makes ``<path>/bin/python``. ``<venv python> -m ensurepip ...`` makes ``<venv>/bin/pip`` once
``release`` is set, so a test decides how long the pip bootstrap takes. Patch ``asyncio.create_subprocess_exec`` of the venv manager
with an instance (``patch(VENV_SPAWN, side_effect=FakeVenvSpawn())``).
"""

from __future__ import annotations

import asyncio
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


class _FakeProcess:
    def __init__(
        self,
        venv_path: Path,
        *,
        creates: bool,
        exit_code: int,
        release: asyncio.Event,
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        self.returncode = exit_code
        self.pid = 0
        self._venv_path = venv_path
        self._creates = creates
        self._release = release
        self._on_cancel = on_cancel

    async def communicate(self) -> tuple[bytes, bytes]:
        if self._creates:
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
        return b"", b"ensurepip failed" if self.returncode else b""


class FakeVenvSpawn:
    """``asyncio.create_subprocess_exec`` as the venv manager calls it."""

    def __init__(
        self,
        *,
        create_exit: int = 0,
        bootstrap_exit: int = 0,
        hold_bootstrap: bool = False,
        bootstrap_error: OSError | None = None,
    ) -> None:
        self.calls: list[Spawned] = []
        self.cancelled_bootstraps = 0
        self.release = asyncio.Event()
        if not hold_bootstrap:
            self.release.set()
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
        env, cwd = kwargs.get("env"), kwargs.get("cwd")
        self.calls.append(Spawned(argv, env if isinstance(env, dict) else None, cwd if isinstance(cwd, str) else None))
        if "ensurepip" in argv:
            if self._bootstrap_error is not None:
                raise self._bootstrap_error
            return _FakeProcess(
                Path(argv[0]).parent.parent,
                creates=False,
                exit_code=self._bootstrap_exit,
                release=self.release,
                on_cancel=self._count_cancelled_bootstrap,
            )
        return _FakeProcess(Path(argv[-1]), creates=True, exit_code=self._create_exit, release=self.release)

    def _count_cancelled_bootstrap(self) -> None:
        self.cancelled_bootstraps += 1
