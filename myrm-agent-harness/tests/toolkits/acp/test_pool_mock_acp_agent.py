"""RuntimePool driving a real ACP agent subprocess (the mock echo agent) end to end."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.acp.runtime.pool import RuntimePool
from myrm_agent_harness.toolkits.acp.types import RuntimeConfig, RuntimeEventType

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="process liveness is probed with POSIX signals")

_MOCK_AGENT = Path(__file__).with_name("_mock_acp_agent.py")


def _mock_pool(cwd: Path) -> RuntimePool:
    pool = RuntimePool(max_concurrent=1)
    pool.register(
        "mock",
        RuntimeConfig(
            backend_type="acp",
            command=sys.executable,
            args=[str(_MOCK_AGENT)],
            cwd=str(cwd),
            timeout_seconds=30,
        ),
    )
    return pool


async def _echo(pool: RuntimePool, prompt: str) -> str:
    text: list[str] = []
    async for event in pool.run_turn("mock", prompt, session_id="chat-1"):
        if event.type == RuntimeEventType.TEXT_DELTA:
            text.append(str(event.data.get("content")))
    return "".join(text)


def _pid_of(pool: RuntimePool) -> int:
    process = getattr(pool.get("mock"), "_process", None)
    assert process is not None
    return int(process.pid)


async def _wait_until_gone(pid: int, *, timeout: float = 5.0) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        await asyncio.sleep(0.05)
    return False


@pytest.mark.asyncio
async def test_pool_round_trips_through_an_acp_process_and_close_all_stops_it(tmp_path: Path) -> None:
    pool = _mock_pool(tmp_path)
    try:
        text = await _echo(pool, "ping")
        pid = _pid_of(pool)
    finally:
        await pool.close_all()

    assert "[echo] ping" in text
    assert await _wait_until_gone(pid)


@pytest.mark.asyncio
async def test_pool_respawns_an_acp_process_that_died_between_turns(tmp_path: Path) -> None:
    """No supervisor is needed: the next turn notices the dead process and starts a new one."""
    pool = _mock_pool(tmp_path)
    try:
        assert "[echo] first" in await _echo(pool, "first")
        dead_pid = _pid_of(pool)
        os.kill(dead_pid, signal.SIGKILL)
        assert await _wait_until_gone(dead_pid)

        assert "[echo] second" in await _echo(pool, "second")
        new_pid = _pid_of(pool)
    finally:
        await pool.close_all()

    assert new_pid != dead_pid
    assert await _wait_until_gone(new_pid)


def _resident(backend: object) -> tuple[int, str]:
    """The (pid, ACP session id) a backend is currently running."""
    process = getattr(backend, "_process", None)
    session_id = getattr(backend, "_session_id", None)
    assert process is not None
    assert session_id is not None
    return int(process.pid), str(session_id)


@pytest.mark.asyncio
async def test_oneshot_runs_in_its_own_process_and_session_and_leaves_the_persistent_one_alone(tmp_path: Path) -> None:
    pool = _mock_pool(tmp_path)
    try:
        assert "[echo] first" in await _echo(pool, "first")
        persistent_pid, persistent_session = _resident(pool.get("mock"))

        oneshot_resident: tuple[int, str] | None = None
        oneshot_backend: object | None = None  # referenced so garbage collection cannot stand in for close()
        oneshot_text: list[str] = []
        async for event in pool.run_turn("mock", "review", session_id="mock-oneshot-1", mode="oneshot"):
            if event.type == RuntimeEventType.TEXT_DELTA:
                oneshot_text.append(str(event.data.get("content")))
                oneshot_backend = pool._oneshot_backends[("mock", "mock-oneshot-1")]
                oneshot_resident = _resident(oneshot_backend)

        assert "[echo] review" in "".join(oneshot_text)
        assert oneshot_resident is not None
        oneshot_pid, oneshot_session = oneshot_resident
        assert oneshot_pid != persistent_pid
        assert oneshot_session != persistent_session
        assert await _wait_until_gone(oneshot_pid)

        # The persistent backend is the same process and session as before the oneshot turn.
        assert "[echo] second" in await _echo(pool, "second")
        assert _resident(pool.get("mock")) == (persistent_pid, persistent_session)
    finally:
        await pool.close_all()


@pytest.mark.asyncio
async def test_release_resident_stops_the_acp_process_and_the_next_turn_starts_a_new_one(tmp_path: Path) -> None:
    pool = _mock_pool(tmp_path)
    try:
        assert "[echo] first" in await _echo(pool, "first")
        released_pid = _pid_of(pool)
        # Keep the backend referenced: an unreferenced one could be torn down by garbage collection
        # and make the process look released even if release_resident never closed it.
        released_backend = pool.get("mock")

        await pool.release_resident()

        assert await _wait_until_gone(released_pid)
        assert released_backend is not pool.get("mock")
        assert "[echo] second" in await _echo(pool, "second")
        new_pid = _pid_of(pool)
    finally:
        await pool.close_all()

    assert new_pid != released_pid
    assert await _wait_until_gone(new_pid)
