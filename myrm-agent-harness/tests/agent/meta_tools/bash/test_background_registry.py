"""Unit tests for the background-process registry: registration, output, progress and reaping."""

from __future__ import annotations

import asyncio
from typing import cast

import pytest

from myrm_agent_harness.agent.meta_tools.bash._background.registry import (
    BackgroundProcessInfo,
    BackgroundProcessRegistry,
)
from myrm_agent_harness.toolkits.code_execution.executors.models import AsyncProcessProtocol
from tests.agent.meta_tools.bash.fake_background_proc import FakeProc, wait_until


@pytest.mark.asyncio
async def test_register_captures_output_and_status_transitions() -> None:
    registry = BackgroundProcessRegistry()
    proc = FakeProc(pid=11111, stdout=[b"line-1\n", b"line-2\n"], stderr=[b"warn\n"])

    info = await registry.register(cast(AsyncProcessProtocol, proc), command="echo hi", session_id="s-1")

    assert isinstance(info, BackgroundProcessInfo)
    assert info.pid == 11111
    assert info.status == "running"

    listed_other = registry.list_processes(session_id="other")
    assert listed_other == []

    listed = registry.list_processes(session_id="s-1")
    assert len(listed) == 1
    assert listed[0].pid == 11111

    proc.finish(0)
    # Deterministically wait for the reader task to flip status instead of
    # guessing a sleep duration (flaky under high load).
    await wait_until(
        lambda: registry.get(11111) is not None and registry.get(11111).status == "exited",  # type: ignore[union-attr]
        what="status transition to exited",
    )

    final = registry.get(11111)
    assert final is not None
    assert final.status == "exited"
    assert final.exit_code == 0

    output = registry.get_output(11111, max_lines=10)
    stdout_lines = cast(list[str], output["stdout"])
    stderr_lines = cast(list[str], output["stderr"])
    assert "line-1" in stdout_lines
    assert "line-2" in stdout_lines
    assert "warn" in stderr_lines
    assert output["dropped"] is False


@pytest.mark.asyncio
async def test_per_session_quota_blocks_new_jobs() -> None:
    registry = BackgroundProcessRegistry(per_session_limit=2)
    procs = [FakeProc(pid=30000 + i, stdout=[], stderr=[]) for i in range(2)]
    for proc in procs:
        await registry.register(cast(AsyncProcessProtocol, proc), command="sleep 10", session_id="quota-s")

    third = FakeProc(pid=30002, stdout=[], stderr=[])
    from myrm_agent_harness.agent.meta_tools.bash._background.registry import (
        BackgroundQuotaError,
    )

    with pytest.raises(BackgroundQuotaError):
        await registry.register(
            cast(AsyncProcessProtocol, third),
            command="sleep 10",
            session_id="quota-s",
        )

    # Releasing one slot must allow the next register.
    procs[0].finish(0)
    await wait_until(
        lambda: registry.get(30000) is not None and registry.get(30000).status != "running",  # type: ignore[union-attr]
        what="slot release for pid 30000",
    )
    await registry.register(cast(AsyncProcessProtocol, third), command="sleep 10", session_id="quota-s")


@pytest.mark.asyncio
async def test_progress_listener_fires_for_explicit_marker() -> None:
    registry = BackgroundProcessRegistry()
    proc = FakeProc(
        pid=44444,
        stdout=[b'MYRM_PROGRESS {"percent": 42, "message": "Compiling"}\n'],
        stderr=[],
    )

    events: list[dict[str, object]] = []

    async def _listener(_info: BackgroundProcessInfo, payload: dict[str, object]) -> None:
        events.append(payload)

    await registry.register(
        cast(AsyncProcessProtocol, proc),
        command="build",
        session_id="prog-s",
        progress_listener=_listener,
    )
    proc.finish(0)
    await wait_until(lambda: len(events) >= 1, what="progress listener dispatch")

    assert len(events) == 1
    assert events[0]["progress"] == 42
    assert events[0]["message"] == "Compiling"


@pytest.mark.asyncio
async def test_output_returns_both_streams_in_full() -> None:
    """One read returns every line of both interleaved streams; neither stream eats into the other's tail."""
    registry = BackgroundProcessRegistry()
    proc = FakeProc(
        pid=66666,
        stdout=[b"out-1\n", b"out-2\n", b"out-3\n"],
        stderr=[b"err-1\n", b"err-2\n"],
    )
    await registry.register(
        cast(AsyncProcessProtocol, proc),
        command="echo",
        session_id="cur-s",
    )
    await wait_until(
        lambda: cast(list[str], registry.get_output(66666, max_lines=10)["stdout"]) == ["out-1", "out-2", "out-3"],
        what="stdout lines ingested",
    )
    first = registry.get_output(66666, max_lines=10)
    assert first["stdout"] == ["out-1", "out-2", "out-3"]
    assert first["stderr"] == ["err-1", "err-2"]
    assert first["dropped"] is False

    proc.finish(0)
    await asyncio.sleep(0.02)


@pytest.mark.asyncio
async def test_finish_listener_invoked_on_exit() -> None:
    registry = BackgroundProcessRegistry()
    proc = FakeProc(pid=55555, stdout=[], stderr=[])

    seen: list[BackgroundProcessInfo] = []

    async def _on_finish(info: BackgroundProcessInfo) -> None:
        seen.append(info)

    await registry.register(
        cast(AsyncProcessProtocol, proc),
        command="sleep 1",
        session_id="fin-s",
        finish_listener=_on_finish,
    )
    proc.finish(0)
    await wait_until(lambda: len(seen) >= 1, what="finish listener dispatch")

    assert len(seen) == 1
    assert seen[0].pid == 55555
    assert seen[0].status == "exited"


@pytest.mark.asyncio
async def test_reap_drops_exited_entries_after_window() -> None:
    """O11: exited entries are reaped from the registry after the reap delay."""
    registry = BackgroundProcessRegistry(reap_delay_seconds=0.05)
    proc = FakeProc(pid=80000, stdout=[b"hi\n"], stderr=[])
    await registry.register(
        cast(AsyncProcessProtocol, proc),
        command="echo hi",
        session_id="reap-s",
    )
    proc.finish(0)
    await wait_until(
        lambda: registry.get(80000) is not None and registry.get(80000).status != "running",  # type: ignore[union-attr]
        what="reap entry to become exited",
    )
    assert registry.get(80000) is not None
    await wait_until(
        lambda: registry.get(80000) is None,
        timeout_seconds=2.0,
        what="reap window to drop entry",
    )
    assert registry.get(80000) is None
    assert registry.list_processes(session_id="reap-s") == []


@pytest.mark.asyncio
async def test_long_line_is_truncated_in_buffer() -> None:
    """O7: a line over 32 Ki characters is clipped to them, with a marker that counts what was dropped."""
    huge = b"x" * (40 * 1024) + b"\n"
    registry = BackgroundProcessRegistry()
    proc = FakeProc(pid=90000, stdout=[huge], stderr=[])
    await registry.register(
        cast(AsyncProcessProtocol, proc),
        command="dump",
        session_id="trunc-s",
    )
    proc.finish(0)
    await wait_until(
        lambda: bool(registry.get_output(90000, max_lines=5)["stdout"]),
        what="truncated line ingestion",
    )

    out = registry.get_output(90000, max_lines=5)
    stdout_lines = cast(list[str], out["stdout"])
    assert len(stdout_lines) == 1
    assert stdout_lines[0].endswith("... [+8192 chars truncated]")
    assert len(stdout_lines[0]) < 40 * 1024


@pytest.mark.asyncio
async def test_last_progress_captured_for_list_processes() -> None:
    """L: list_processes returns the most recent progress payload + updated_at.

    LLM polling multiple background jobs can read percent/message in a single
    list call without paying for per-pid output fetches. ``updated_at`` lets
    the model detect stale snapshots (job stopped emitting minutes ago).
    """
    registry = BackgroundProcessRegistry()
    proc = FakeProc(
        pid=12121,
        stdout=[
            b'MYRM_PROGRESS {"percent": 25, "message": "Compiling"}\n',
            b'MYRM_PROGRESS {"percent": 80, "message": "Linking"}\n',
        ],
        stderr=[],
    )
    await registry.register(
        cast(AsyncProcessProtocol, proc),
        command="cargo build",
        session_id="L-s",
    )

    # Drive both progress markers through the reader task.
    def _progress_80() -> bool:
        items = registry.list_processes(session_id="L-s")
        if not items or items[0].last_progress is None:
            return False
        return cast(dict[str, object], items[0].last_progress)["progress"] == 80

    await wait_until(_progress_80, what="both progress markers processed")

    listed = registry.list_processes(session_id="L-s")
    assert len(listed) == 1
    progress = listed[0].last_progress
    assert progress is not None
    # The newest payload must win — registry must not return the first 25% one.
    assert progress["progress"] == 80
    assert progress["message"] == "Linking"
    assert isinstance(progress["updated_at"], float)

    # to_dict() exposes the same fields for LLM JSON serialisation.
    payload = listed[0].to_dict()
    assert "last_progress" in payload
    assert cast(dict[str, object], payload["last_progress"])["progress"] == 80

    # Defensive copy: mutating the returned payload must not bleed back.
    cast(dict[str, object], listed[0].last_progress)["progress"] = 999
    fresh = registry.list_processes(session_id="L-s")[0]
    assert cast(dict[str, object], fresh.last_progress)["progress"] == 80

    proc.finish(0)
    await asyncio.sleep(0.02)


@pytest.mark.asyncio
async def test_list_processes_omits_last_progress_when_unseen() -> None:
    """``to_dict`` must not include ``last_progress`` for jobs without progress."""
    registry = BackgroundProcessRegistry()
    proc = FakeProc(pid=13131, stdout=[b"plain output\n"], stderr=[])
    await registry.register(
        cast(AsyncProcessProtocol, proc),
        command="echo plain",
        session_id="np-s",
    )
    await wait_until(
        lambda: (
            bool(registry.list_processes(session_id="np-s"))
            and registry.list_processes(session_id="np-s")[0].last_progress is None
        ),
        what="plain output ingested without progress",
    )
    payload = registry.list_processes(session_id="np-s")[0].to_dict()
    assert "last_progress" not in payload
    proc.finish(0)
    await asyncio.sleep(0.02)


@pytest.mark.asyncio
async def test_list_processes_without_session_returns_all() -> None:
    """Unfiltered list must include every registered session."""
    registry = BackgroundProcessRegistry()
    proc_a = FakeProc(pid=17001, stdout=[], stderr=[])
    proc_b = FakeProc(pid=17002, stdout=[], stderr=[])
    await registry.register(cast(AsyncProcessProtocol, proc_a), command="a", session_id="sess-a")
    await registry.register(cast(AsyncProcessProtocol, proc_b), command="b", session_id="sess-b")

    listed = registry.list_processes()
    pids = {row.pid for row in listed}
    assert pids == {17001, 17002}


@pytest.mark.asyncio
async def test_register_redacts_command_in_background_info() -> None:
    """Registering a command with credentials must redact them in BackgroundProcessInfo."""
    registry = BackgroundProcessRegistry()
    proc = FakeProc(pid=17003, stdout=[], stderr=[])
    info = await registry.register(
        cast(AsyncProcessProtocol, proc),
        command="export ANTHROPIC_API_KEY=sk-ant-api03-abcdefghijklmnop1234567890",
        session_id="sess-secret",
    )
    assert "sk-ant-api03" not in info.command
    assert "..." in info.command or "***" in info.command


def test_get_output_unknown_pid_returns_empty_snapshot() -> None:
    registry = BackgroundProcessRegistry()
    assert registry.get_output(99999) == {"stdout": [], "stderr": [], "dropped": False}


def test_get_background_registry_returns_singleton() -> None:
    from myrm_agent_harness.agent.meta_tools.bash._background import registry as mod

    mod._registry = None
    first = mod.get_background_registry()
    second = mod.get_background_registry()
    assert first is second
