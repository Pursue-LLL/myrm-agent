"""A hung external agent must not wedge ChatRuntimePoolRegistry (pool close is bounded)."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.external_agents import runtime_pool_registry
from app.services.external_agents.runtime_pool_registry import (
    ChatRuntimePoolRegistry,
    close_runtime_pool_bounded,
)

_TEST_CLOSE_TIMEOUT = 0.1
_LOGGER_NAME = runtime_pool_registry.__name__


@pytest.fixture(autouse=True)
def _short_close_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime_pool_registry, "_POOL_CLOSE_TIMEOUT_SECONDS", _TEST_CLOSE_TIMEOUT)


async def _hang_forever() -> None:
    """Stands in for an ACP agent that stays alive but never answers ``session/close``."""
    await asyncio.Event().wait()


def _hung_pool() -> MagicMock:
    pool = MagicMock()
    pool.available_backends = ["acp"]
    pool.close_all = AsyncMock(side_effect=_hang_forever)
    pool.release_resident = AsyncMock(side_effect=_hang_forever)
    return pool


def _healthy_pool() -> MagicMock:
    pool = MagicMock()
    pool.available_backends = ["claude"]
    pool.close_all = AsyncMock()
    pool.release_resident = AsyncMock()
    return pool


def _pool_builder(pool: MagicMock) -> Callable[[], Awaitable[MagicMock]]:
    async def build_pool() -> MagicMock:
        return pool

    return build_pool


@pytest.mark.asyncio
async def test_hung_pool_during_idle_release_does_not_freeze_other_chats(caplog: pytest.LogCaptureFixture) -> None:
    registry = ChatRuntimePoolRegistry(idle_seconds=0.01)
    hung = _hung_pool()
    await registry.acquire("chat-hung", "fp-a", _pool_builder(hung))
    await asyncio.sleep(0.02)

    healthy = _healthy_pool()
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        acquired = await asyncio.wait_for(registry.acquire("chat-ok", "fp-a", _pool_builder(healthy)), timeout=2.0)

    assert acquired is healthy
    hung.release_resident.assert_awaited_once()
    assert registry._entries["chat-hung"].pool is hung
    assert "runtime_pool_release_timeout scope=chat-hung" in caplog.text
    # The registry lock is free again: later calls do not queue behind the hung close.
    await asyncio.wait_for(registry.release("chat-ok"), timeout=1.0)


@pytest.mark.asyncio
async def test_close_all_closes_pools_concurrently_and_continues_past_hung_pools() -> None:
    registry = ChatRuntimePoolRegistry(idle_seconds=3600.0)
    hung_pools = [_hung_pool() for _ in range(3)]
    healthy = _healthy_pool()
    for index, pool in enumerate([*hung_pools, healthy]):
        await registry.acquire(f"chat-{index}", "fp-a", _pool_builder(pool))

    started = time.monotonic()
    await asyncio.wait_for(registry.close_all(), timeout=2.0)
    elapsed = time.monotonic() - started

    healthy.close_all.assert_awaited_once()
    for pool in hung_pools:
        pool.close_all.assert_awaited_once()
    assert registry._entries == {}
    assert registry._turn_locks == {}
    # Sequential closes would take 3 * timeout; concurrent ones stay near a single timeout.
    assert elapsed < _TEST_CLOSE_TIMEOUT * 2.5


@pytest.mark.asyncio
async def test_close_chat_with_hung_pool_returns_and_cleans_entry_and_turn_lock() -> None:
    registry = ChatRuntimePoolRegistry(idle_seconds=3600.0)
    hung = _hung_pool()
    await registry.acquire("chat-1", "fp-a", _pool_builder(hung))
    async with registry.guard_turn("chat-1"):
        pass

    await asyncio.wait_for(registry.close_chat("chat-1"), timeout=2.0)

    hung.close_all.assert_awaited_once()
    assert registry._entries == {}
    assert registry._turn_locks == {}


@pytest.mark.asyncio
async def test_close_runtime_pool_bounded_swallows_failures_but_not_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failing = _healthy_pool()
    failing.close_all = AsyncMock(side_effect=RuntimeError("boom"))
    await close_runtime_pool_bounded(failing, scope="chat-err")
    failing.close_all.assert_awaited_once()

    monkeypatch.setattr(runtime_pool_registry, "_POOL_CLOSE_TIMEOUT_SECONDS", 30.0)
    closing = asyncio.create_task(close_runtime_pool_bounded(_hung_pool(), scope="chat-cancel"))
    await asyncio.sleep(0.01)
    closing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await closing
