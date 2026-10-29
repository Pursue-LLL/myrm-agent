"""Enforcement tests for the snapshot deadline against real child processes: runtime binaries that hang.

[INPUT]
- agent.workspace_rules.middleware::_acquire_snapshot (POS: takes the snapshot of a thread's workspace under a deadline)
- toolkits.code_execution.sandbox_snapshot (POS: sandbox bootstrap snapshot generator, never mocked here)
- executables in a temp directory that is the whole PATH (POS: real child processes that never answer)

[OUTPUT]
- Fails when a snapshot whose runtime binaries hang is waited for past the deadline, or is not left empty.

[POS]
The other deadline tests hang a stand-in generator. This one hangs the real processes the generator starts, so
the deadline, the generator and the subprocess calls are exercised together.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import threading
import time
from pathlib import Path

import pytest

from myrm_agent_harness.agent.workspace_rules import middleware
from myrm_agent_harness.toolkits.code_execution import sandbox_snapshot

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the stubs are POSIX shell scripts")

_HUNG_RUNTIMES = ("python3", "python", "node")
_PER_COMMAND_TIMEOUT_S = 0.4
_DEADLINE_MS = 300.0


@pytest.fixture
def hung_runtimes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Runtime binaries that never answer, as the whole PATH; the workspace to probe is returned."""
    sleep = shutil.which("sleep")
    assert sleep, "the stubs need an absolute path to sleep, because their PATH holds nothing else"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in _HUNG_RUNTIMES:
        script = bin_dir / name
        # exec replaces the shell, so the probe's timeout kills the sleeper itself and no orphan outlives it.
        script.write_text(f"#!/bin/sh\nexec {sleep} 30\n")
        script.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


def _probe_threads() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name == "workspace-snapshot" and t.is_alive()]


@pytest.mark.asyncio
async def test_a_snapshot_whose_runtimes_hang_is_cut_off_at_the_deadline_and_left_empty(
    hung_runtimes: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    quick_command = sandbox_snapshot._run_quick_command
    monkeypatch.setattr(
        sandbox_snapshot,
        "_run_quick_command",
        lambda cmd, timeout=1.0, **kwargs: quick_command(cmd, _PER_COMMAND_TIMEOUT_S, **kwargs),
    )
    monkeypatch.setattr(middleware, "_SNAPSHOT_DEADLINE_MS", _DEADLINE_MS)

    started = time.perf_counter()
    snapshot = await middleware._acquire_snapshot(str(hung_runtimes))
    waited = time.perf_counter() - started
    still_probing = bool(_probe_threads())

    # The probe needs one timeout per hung binary; let it finish while the patched PATH is still in place.
    try:
        assert snapshot == "", "an abandoned probe must leave the empty snapshot"
        assert waited < len(_HUNG_RUNTIMES) * _PER_COMMAND_TIMEOUT_S, f"waited {waited:.2f} s, past the deadline"
        assert still_probing, "the probe was not cut off mid-flight: it had already finished"
    finally:
        for _ in range(100):
            if not _probe_threads():
                break
            await asyncio.sleep(0.05)
