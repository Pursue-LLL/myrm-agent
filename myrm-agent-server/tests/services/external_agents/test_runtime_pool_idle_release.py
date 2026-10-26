"""Idle release of chat-scoped RuntimePools: resident processes are freed, the pool and its CLI resume state stay."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.external_agents.runtime_pool_registry import ChatRuntimePoolRegistry


async def _build_mock_pool() -> MagicMock:
    pool = MagicMock()
    pool.available_backends = ["claude"]
    pool.close_all = AsyncMock()
    pool.release_resident = AsyncMock()
    return pool


async def _unexpected_build() -> MagicMock:
    raise AssertionError("the existing pool must be reused, not rebuilt")


@pytest.mark.asyncio
async def test_idle_pool_releases_resident_backends_and_stays_registered() -> None:
    """Idle cleanup frees processes but must keep the pool: its CLI backends hold the --resume ids."""
    registry = ChatRuntimePoolRegistry(idle_seconds=0.01)
    pool = await registry.acquire("chat-1", "fp-a", _build_mock_pool)
    await registry.release("chat-1")
    await asyncio.sleep(0.02)

    await registry.acquire("chat-2", "fp-a", _build_mock_pool)

    pool.release_resident.assert_awaited_once()
    pool.close_all.assert_not_called()
    assert await registry.acquire("chat-1", "fp-a", _unexpected_build) is pool


@pytest.mark.asyncio
async def test_a_chat_asking_for_its_pool_after_the_idle_window_keeps_it_as_it_was() -> None:
    """The chat that comes back is in use, not idle: its own acquire neither rebuilds nor releases its pool."""
    registry = ChatRuntimePoolRegistry(idle_seconds=0.01)
    pool = await registry.acquire("chat-1", "fp-a", _build_mock_pool)
    await asyncio.sleep(0.02)

    assert await registry.acquire("chat-1", "fp-a", _unexpected_build) is pool
    pool.release_resident.assert_not_called()
    pool.close_all.assert_not_called()


@pytest.mark.asyncio
async def test_released_pool_is_released_again_only_after_it_was_used() -> None:
    registry = ChatRuntimePoolRegistry(idle_seconds=0.02)
    pool = await registry.acquire("chat-1", "fp-a", _build_mock_pool)
    await asyncio.sleep(0.03)

    await registry.acquire("chat-2", "fp-a", _build_mock_pool)
    await registry.acquire("chat-3", "fp-a", _build_mock_pool)
    assert pool.release_resident.await_count == 1

    async with registry.guard_turn("chat-1"):
        pass
    await asyncio.sleep(0.03)
    await registry.acquire("chat-4", "fp-a", _build_mock_pool)
    assert pool.release_resident.await_count == 2


@pytest.mark.asyncio
async def test_idle_release_skips_pool_with_turn_in_flight() -> None:
    """A delegation that outlives the idle window keeps its processes and its turn lock."""
    registry = ChatRuntimePoolRegistry(idle_seconds=0.02)
    pool = await registry.acquire("chat-1", "fp-a", _build_mock_pool)
    started = asyncio.Event()
    release = asyncio.Event()
    running = 0
    peak_running = 0

    async def turn() -> None:
        nonlocal running, peak_running
        async with registry.guard_turn("chat-1"):
            running += 1
            peak_running = max(peak_running, running)
            started.set()
            await release.wait()
            running -= 1

    first = asyncio.create_task(turn())
    await started.wait()
    await asyncio.sleep(0.05)
    await registry.acquire("chat-2", "fp-a", _build_mock_pool)

    pool.release_resident.assert_not_called()
    pool.close_all.assert_not_called()
    assert await registry.acquire("chat-1", "fp-a", _unexpected_build) is pool

    second = asyncio.create_task(turn())
    await asyncio.sleep(0.01)
    assert peak_running == 1
    release.set()
    await asyncio.gather(first, second)
    assert peak_running == 1


@pytest.mark.asyncio
async def test_guard_turn_exit_restarts_idle_clock() -> None:
    """A turn longer than the idle window must not get its processes released the moment it ends."""
    registry = ChatRuntimePoolRegistry(idle_seconds=0.05)
    pool = await registry.acquire("chat-1", "fp-a", _build_mock_pool)

    async with registry.guard_turn("chat-1"):
        await asyncio.sleep(0.08)
    await registry.acquire("chat-2", "fp-a", _build_mock_pool)
    pool.release_resident.assert_not_called()

    await asyncio.sleep(0.08)
    await registry.acquire("chat-3", "fp-a", _build_mock_pool)
    pool.release_resident.assert_awaited_once()


@pytest.mark.asyncio
async def test_guard_turn_restarts_idle_clock_when_turn_fails() -> None:
    registry = ChatRuntimePoolRegistry(idle_seconds=0.05)
    pool = await registry.acquire("chat-1", "fp-a", _build_mock_pool)

    with pytest.raises(RuntimeError, match="delegation failed"):
        async with registry.guard_turn("chat-1"):
            await asyncio.sleep(0.08)
            raise RuntimeError("delegation failed")
    await registry.acquire("chat-2", "fp-a", _build_mock_pool)

    pool.release_resident.assert_not_called()


@pytest.mark.asyncio
async def test_cancelled_idle_release_keeps_the_pool_registered() -> None:
    """A release interrupted by cancellation must not leave the pool unregistered (its processes untracked)."""
    registry = ChatRuntimePoolRegistry(idle_seconds=0.01)
    started = asyncio.Event()

    async def never_returns() -> None:
        started.set()
        await asyncio.Event().wait()

    pool = await registry.acquire("chat-1", "fp-a", _build_mock_pool)
    pool.release_resident = AsyncMock(side_effect=never_returns)
    await asyncio.sleep(0.02)

    releasing = asyncio.create_task(registry.acquire("chat-2", "fp-a", _build_mock_pool))
    await asyncio.wait_for(started.wait(), timeout=1.0)
    releasing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await releasing

    assert registry._entries["chat-1"].pool is pool
    await asyncio.wait_for(registry.release("chat-1"), timeout=1.0)


@pytest.mark.asyncio
async def test_failed_idle_release_keeps_the_pool_registered(caplog: pytest.LogCaptureFixture) -> None:
    registry = ChatRuntimePoolRegistry(idle_seconds=0.01)
    pool = await registry.acquire("chat-1", "fp-a", _build_mock_pool)
    pool.release_resident = AsyncMock(side_effect=RuntimeError("boom"))
    await asyncio.sleep(0.02)

    with caplog.at_level("WARNING"):
        await registry.acquire("chat-2", "fp-a", _build_mock_pool)

    assert registry._entries["chat-1"].pool is pool
    assert "runtime_pool_release_failed scope=chat-1" in caplog.text
