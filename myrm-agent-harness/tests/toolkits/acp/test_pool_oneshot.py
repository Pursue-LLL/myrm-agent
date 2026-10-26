"""RuntimePool oneshot turns: private backend, cancel routing and shutdown coverage.

A ``oneshot`` turn runs on its own backend, so it never touches the shared (persistent) backend.
The real-process form of this contract lives in ``test_pool_cli_resume.py`` and
``test_pool_mock_acp_agent.py``; these tests pin the bookkeeping around it with backend doubles.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest

from myrm_agent_harness.toolkits.acp.runtime.pool import RuntimePool
from myrm_agent_harness.toolkits.acp.types import (
    BackendCapabilities,
    BackendInfo,
    RuntimeConfig,
    RuntimeEvent,
    RuntimeEventType,
    create_event,
)

_POOL_FACTORY = "myrm_agent_harness.toolkits.acp.runtime.pool._create_runtime"
_WAIT_SECONDS = 5


class _FakeBackend:
    """Backend double that echoes the prompt; a turn can block until released or fail."""

    name = "fake"
    capabilities = BackendCapabilities()
    is_alive = True

    def __init__(self, *, gated: bool = False, fail: bool = False) -> None:
        self.gated = gated
        self.fail = fail
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled: list[str] = []
        self.closed = False

    async def run_turn(self, prompt: str, session_id: str, *, mcp_servers=None) -> AsyncIterator[RuntimeEvent]:
        self.started.set()
        if self.fail:
            raise RuntimeError("boom")
        if self.gated:
            await self.release.wait()
        yield create_event(RuntimeEventType.TEXT_DELTA, session_id, content=prompt)
        yield create_event(RuntimeEventType.DONE, session_id, stop_reason="end_turn")

    async def cancel(self, session_id: str) -> None:
        self.cancelled.append(session_id)

    async def resume(self, session_id: str) -> bool:
        return False

    async def get_info(self) -> BackendInfo:
        return BackendInfo(name=self.name)

    async def close(self) -> None:
        self.closed = True


def _pool() -> RuntimePool:
    pool = RuntimePool()
    pool.register("claude", RuntimeConfig(backend_type="cli", command="claude"))
    return pool


async def _drain(stream: AsyncIterator[RuntimeEvent]) -> list[RuntimeEvent]:
    return [event async for event in stream]


@pytest.mark.asyncio
async def test_oneshot_never_touches_the_persistent_backend() -> None:
    pool = _pool()
    persistent = _FakeBackend()
    oneshot = _FakeBackend()

    with patch(_POOL_FACTORY, side_effect=[persistent, oneshot]):
        assert pool.get("claude") is persistent
        await pool.prompt("claude", "review", mode="oneshot")

    assert oneshot.closed
    assert not persistent.closed
    assert pool.get("claude") is persistent


@pytest.mark.asyncio
async def test_oneshot_backend_is_unregistered_and_closed_when_the_turn_fails() -> None:
    pool = _pool()
    backend = _FakeBackend(fail=True)

    with patch(_POOL_FACTORY, return_value=backend), pytest.raises(RuntimeError, match="boom"):
        await _drain(pool.run_turn("claude", "task", "claude-oneshot-1", mode="oneshot"))

    assert backend.closed
    assert pool._oneshot_backends == {}


@pytest.mark.asyncio
async def test_oneshot_unknown_backend_raises_key_error() -> None:
    with pytest.raises(KeyError, match="Unknown backend"):
        await _drain(RuntimePool().run_turn("nonexistent", "task", "s-1", mode="oneshot"))


@pytest.mark.asyncio
async def test_cancel_routes_to_the_in_flight_oneshot_backend() -> None:
    pool = _pool()
    persistent = _FakeBackend()
    oneshot = _FakeBackend(gated=True)

    with patch(_POOL_FACTORY, side_effect=[persistent, oneshot]):
        pool.get("claude")
        turn = asyncio.create_task(_drain(pool.run_turn("claude", "task", "claude-oneshot-1", mode="oneshot")))
        await asyncio.wait_for(oneshot.started.wait(), timeout=_WAIT_SECONDS)
        await pool.cancel("claude", "claude-oneshot-1")
        oneshot.release.set()
        await turn

    assert oneshot.cancelled == ["claude-oneshot-1"]
    assert persistent.cancelled == []


@pytest.mark.asyncio
async def test_cancel_of_a_persistent_session_ignores_a_running_oneshot() -> None:
    pool = _pool()
    persistent = _FakeBackend()
    oneshot = _FakeBackend(gated=True)

    with patch(_POOL_FACTORY, side_effect=[persistent, oneshot]):
        pool.get("claude")
        turn = asyncio.create_task(_drain(pool.run_turn("claude", "task", "claude-oneshot-1", mode="oneshot")))
        await asyncio.wait_for(oneshot.started.wait(), timeout=_WAIT_SECONDS)
        await pool.cancel("claude", "claude-chat-1")
        oneshot.release.set()
        await turn

    assert persistent.cancelled == ["claude-chat-1"]
    assert oneshot.cancelled == []


@pytest.mark.asyncio
async def test_close_all_closes_in_flight_oneshot_backends() -> None:
    pool = _pool()
    oneshot = _FakeBackend(gated=True)

    with patch(_POOL_FACTORY, return_value=oneshot):
        turn = asyncio.create_task(_drain(pool.run_turn("claude", "task", "claude-oneshot-1", mode="oneshot")))
        await asyncio.wait_for(oneshot.started.wait(), timeout=_WAIT_SECONDS)
        await pool.close_all()
        assert oneshot.closed
        oneshot.release.set()
        await turn
