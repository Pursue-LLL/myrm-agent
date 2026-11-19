"""A host without an OS sandbox, the way a container runs background jobs, for the real-model tests of the pseudo-terminal spawn.

[INPUT]
- myrm_agent_harness.toolkits.code_execution.sandbox::detect_sandbox_provider (POS: auto-detect the best available sandbox provider; the one part of the host that is stood in for)
- myrm_agent_harness.toolkits.code_execution.executors.local._background_pty_spawn::try_spawn_background_pty (POS: POSIX PTY spawn adapter; recorded where it is called, then run as it is)

[OUTPUT]
- without_os_sandbox: the probe answers "no OS sandbox", as it does inside a container
- record_pty_spawns: whether each pseudo-terminal spawn of the test produced a process

[POS]
A developer Mac has its sandbox on, so a background job takes the pipe path there; a container has none and spawns every background job on a
pseudo-terminal. The recorder tells a test that the job really ran on one, and did not fall back to pipes.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.code_execution import sandbox
from myrm_agent_harness.toolkits.code_execution.executors.local import _background_pty_spawn
from myrm_agent_harness.toolkits.code_execution.executors.models import AsyncProcessProtocol
from myrm_agent_harness.toolkits.code_execution.platform import PlatformInfo
from myrm_agent_harness.toolkits.code_execution.sandbox.providers.null import NullProvider
from myrm_agent_harness.toolkits.code_execution.sandbox.sandbox_types import SandboxMode, SandboxProvider, SandboxStatus

_NO_OS_SANDBOX = SandboxStatus(enabled=False, provider_name="null", reason="container environment detected")


def _probe_without_os_sandbox(
    mode: SandboxMode = SandboxMode.AUTO, platform_info: PlatformInfo | None = None
) -> tuple[SandboxProvider, SandboxStatus]:
    return NullProvider(), _NO_OS_SANDBOX


def without_os_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inside a container the probe finds no OS sandbox to use, because the container is the sandbox."""
    monkeypatch.setattr(sandbox, "detect_sandbox_provider", _probe_without_os_sandbox)


def record_pty_spawns(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """The outcome of every pseudo-terminal spawn from now on: whether it produced a process; a refusal sends the job to pipes."""
    outcomes: list[bool] = []
    spawn = _background_pty_spawn.try_spawn_background_pty

    async def record(
        *,
        full_cmd_array: list[str],
        effective_cwd: Path | None,
        env: dict[str, str],
        preexec_fn: Callable[[], None] | None,
        process_group_kwargs: dict[str, object],
    ) -> AsyncProcessProtocol | None:
        process = await spawn(
            full_cmd_array=full_cmd_array,
            effective_cwd=effective_cwd,
            env=env,
            preexec_fn=preexec_fn,
            process_group_kwargs=process_group_kwargs,
        )
        outcomes.append(process is not None)
        return process

    monkeypatch.setattr(_background_pty_spawn, "try_spawn_background_pty", record)
    return outcomes
