"""The registry stops jobs: ``kill`` and its SIGTERM-to-SIGKILL escalation, ``kill_session_jobs`` and ``shutdown``."""

from __future__ import annotations

import asyncio
import signal
from typing import cast
from unittest.mock import patch

import pytest

from myrm_agent_harness.agent.meta_tools.bash._background.registry import BackgroundProcessRegistry
from myrm_agent_harness.toolkits.code_execution.executors.models import AsyncProcessProtocol
from tests.agent.meta_tools.bash.fake_background_proc import FakeProc, wait_until


@pytest.mark.asyncio
async def test_kill_terminates_and_marks_status() -> None:
    registry = BackgroundProcessRegistry()
    proc = FakeProc(pid=22222, stdout=[], stderr=[])
    await registry.register(cast(AsyncProcessProtocol, proc), command="sleep 60", session_id="s-2")

    sent: list[tuple[int, int]] = []

    def _record(pid: int, sig: int) -> None:
        sent.append((pid, sig))
        proc.finish(-sig)

    with patch(
        "myrm_agent_harness.agent.meta_tools.bash._background.termination.kill_spawned_group",
        side_effect=_record,
    ):
        ok = await registry.kill(22222, force=False)
    assert ok is True
    assert sent == [(22222, signal.SIGTERM)]

    await wait_until(
        lambda: registry.get(22222) is not None and registry.get(22222).status == "killed",  # type: ignore[union-attr]
        what="status transition to killed",
    )
    snap = registry.get(22222)
    assert snap is not None
    assert snap.status == "killed"


@pytest.mark.asyncio
async def test_kill_unknown_pid_returns_false() -> None:
    registry = BackgroundProcessRegistry()
    ok = await registry.kill(99999)
    assert ok is False


@pytest.mark.asyncio
async def test_kill_escalates_to_sigkill_when_sigterm_ignored() -> None:
    """O5: an unruly child that ignores SIGTERM is force-killed after grace."""
    registry = BackgroundProcessRegistry()
    proc = FakeProc(pid=70000, stdout=[], stderr=[])
    await registry.register(
        cast(AsyncProcessProtocol, proc),
        command="dev-server",
        session_id="esc-s",
    )

    sent: list[tuple[int, int]] = []

    def _record(pid: int, sig: int) -> None:
        sent.append((pid, sig))
        # SIGTERM is recorded but the process keeps running (no finish).
        # Only SIGKILL actually drops it, matching real-world unruly processes.
        if sig == signal.SIGKILL:
            proc.finish(-9)

    with patch(
        "myrm_agent_harness.agent.meta_tools.bash._background.termination.kill_spawned_group",
        side_effect=_record,
    ):
        ok = await registry.kill(70000, force=False, grace_seconds=0.1)

    assert ok is True
    assert sent == [(70000, signal.SIGTERM), (70000, signal.SIGKILL)]

    await wait_until(
        lambda: registry.get(70000) is not None and registry.get(70000).status == "killed",  # type: ignore[union-attr]
        what="SIGKILL status transition",
    )
    snap = registry.get(70000)
    assert snap is not None
    assert snap.status == "killed"


@pytest.mark.asyncio
async def test_kill_session_jobs_only_targets_owner_session() -> None:
    """O: kill_session_jobs must signal exactly the owner session's jobs."""
    registry = BackgroundProcessRegistry()
    proc_a1 = FakeProc(pid=14001, stdout=[], stderr=[])
    proc_a2 = FakeProc(pid=14002, stdout=[], stderr=[])
    proc_b = FakeProc(pid=14003, stdout=[], stderr=[])
    await registry.register(cast(AsyncProcessProtocol, proc_a1), command="sleep 60", session_id="chat-A")
    await registry.register(cast(AsyncProcessProtocol, proc_a2), command="sleep 60", session_id="chat-A")
    await registry.register(cast(AsyncProcessProtocol, proc_b), command="sleep 60", session_id="chat-B")

    sent: list[tuple[int, int]] = []

    def _record(pid: int, sig: int) -> None:
        sent.append((pid, sig))
        if pid == 14001:
            proc_a1.finish(-sig)
        elif pid == 14002:
            proc_a2.finish(-sig)
        elif pid == 14003:
            proc_b.finish(-sig)

    with patch(
        "myrm_agent_harness.agent.meta_tools.bash._background.termination.kill_spawned_group",
        side_effect=_record,
    ):
        killed = await registry.kill_session_jobs("chat-A", grace_seconds=0.05)

    assert killed == 2
    # Only chat-A pids must have been signalled. ``sent`` may also contain
    # SIGKILL escalations for pids that ignore SIGTERM in real life, but our
    # _record finishes the proc on SIGTERM so SIGKILL never fires.
    signalled_pids = {pid for pid, _ in sent}
    assert signalled_pids == {14001, 14002}

    snap_b = registry.get(14003)
    assert snap_b is not None
    assert snap_b.status == "running"
    proc_b.finish(0)
    await asyncio.sleep(0.02)


@pytest.mark.asyncio
async def test_kill_session_jobs_returns_zero_when_no_match() -> None:
    """O: kill_session_jobs is a no-op for sessions with no running jobs."""
    registry = BackgroundProcessRegistry()
    killed = await registry.kill_session_jobs("nobody-here")
    assert killed == 0


@pytest.mark.asyncio
async def test_kill_session_jobs_runs_concurrently() -> None:
    """O: 5 stubborn jobs × 0.2s grace must finish in <1.5s (not 5×0.2=1.0s sequentially).

    Concurrency guard against future refactors that loop ``await self.kill``
    serially — that would scale ``cancel`` latency with bg job count.
    """
    registry = BackgroundProcessRegistry()
    pids = list(range(15001, 15006))
    procs = [FakeProc(pid=p, stdout=[], stderr=[]) for p in pids]
    for proc in procs:
        await registry.register(
            cast(AsyncProcessProtocol, proc),
            command="dev-server",
            session_id="concurrent-s",
        )

    pid_to_proc = dict(zip(pids, procs, strict=False))

    def _record(pid: int, sig: int) -> None:
        # SIGTERM is recorded but ignored — these jobs are "stubborn"; the
        # registry must escalate to SIGKILL after the grace window. If
        # kill_session_jobs awaited each kill() serially the total wall time
        # would be ≥ 5 × grace; concurrent dispatch keeps it near 1 × grace.
        if sig == signal.SIGKILL:
            pid_to_proc[pid].finish(-9)

    loop = asyncio.get_running_loop()
    start = loop.time()
    with patch(
        "myrm_agent_harness.agent.meta_tools.bash._background.termination.kill_spawned_group",
        side_effect=_record,
    ):
        killed = await registry.kill_session_jobs("concurrent-s", grace_seconds=0.2)
    elapsed = loop.time() - start

    assert killed == 5
    # Concurrent: ≈ 1 × grace (0.2s) + escalation buffer; serial would be ≥5×grace = 1.0s.
    # Allow generous headroom for CI noise.
    assert elapsed < 0.8, f"kill_session_jobs ran serially? elapsed={elapsed:.2f}s"


@pytest.mark.asyncio
async def test_shutdown_uses_process_group_kill_for_living_children() -> None:
    """``atexit`` path must route through process-group kill, not leader-only.

    Mirrors the live ``kill`` contract (PR2.6 O12): leader-only ``proc.kill()``
    would orphan ``node``/``esbuild`` grandchildren under ``npm start`` when the
    Python harness exits — process-group SIGKILL severs the whole tree.
    """
    registry = BackgroundProcessRegistry()
    proc_running = FakeProc(pid=16001, stdout=[], stderr=[])
    proc_exited = FakeProc(pid=16002, stdout=[], stderr=[])
    await registry.register(cast(AsyncProcessProtocol, proc_running), command="npm start", session_id="s1")
    await registry.register(cast(AsyncProcessProtocol, proc_exited), command="echo done", session_id="s1")
    proc_exited.finish(0)
    # Deterministically let the consumer loop transition proc_exited → exited
    # before shutdown runs (a fixed sleep is flaky under load).
    await wait_until(
        lambda: registry.get(16002) is not None and registry.get(16002).status != "running",  # type: ignore[union-attr]
        what="proc_exited transition before shutdown",
    )

    killed_pids: list[tuple[int, int]] = []

    def _record(pid: int, sig: int) -> None:
        killed_pids.append((pid, sig))

    with patch(
        "myrm_agent_harness.agent.meta_tools.bash._background.termination.kill_spawned_group",
        side_effect=_record,
    ):
        registry.shutdown()

    assert killed_pids == [(16001, signal.SIGKILL)], (
        f"shutdown must SIGKILL only the still-running pid via group kill; got {killed_pids}"
    )


@pytest.mark.asyncio
async def test_kill_non_running_pid_is_noop_success() -> None:
    registry = BackgroundProcessRegistry()
    proc = FakeProc(pid=18001, stdout=[], stderr=[])
    await registry.register(cast(AsyncProcessProtocol, proc), command="echo done", session_id="done-s")
    proc.finish(0)
    await wait_until(
        lambda: registry.get(18001) is not None and registry.get(18001).status != "running",  # type: ignore[union-attr]
        what="pid 18001 to exit",
    )

    ok = await registry.kill(18001)
    assert ok is True
