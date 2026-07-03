"""Tests for chat-scoped RuntimePool registry."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.external_agents.runtime_pool_registry import (
    ChatRuntimePoolRegistry,
    ChatScopedRuntimePoolFacade,
    get_chat_runtime_pool_registry,
)


@pytest.fixture(autouse=True)
async def _reset_registry_singleton() -> None:
    await get_chat_runtime_pool_registry().close_all()
    yield
    await get_chat_runtime_pool_registry().close_all()


@pytest.mark.asyncio
async def test_acquire_reuses_pool_for_same_chat_and_fingerprint() -> None:
    registry = ChatRuntimePoolRegistry(idle_seconds=3600.0)
    build_count = 0

    async def build_pool() -> MagicMock:
        nonlocal build_count
        build_count += 1
        pool = MagicMock()
        pool.available_backends = ["claude"]
        pool.close_all = AsyncMock()
        return pool

    first = await registry.acquire("chat-1", "fp-a", build_pool)
    second = await registry.acquire("chat-1", "fp-a", build_pool)

    assert first is second
    assert build_count == 1
    first.close_all.assert_not_called()


@pytest.mark.asyncio
async def test_acquire_replaces_pool_when_fingerprint_changes() -> None:
    registry = ChatRuntimePoolRegistry(idle_seconds=3600.0)
    pools: list[MagicMock] = []

    async def build_pool() -> MagicMock:
        pool = MagicMock()
        pool.available_backends = ["claude"]
        pool.close_all = AsyncMock()
        pools.append(pool)
        return pool

    first = await registry.acquire("chat-1", "fp-a", build_pool)
    second = await registry.acquire("chat-1", "fp-b", build_pool)

    assert first is not second
    assert len(pools) == 2
    first.close_all.assert_awaited_once()


@pytest.mark.asyncio
async def test_release_does_not_close_pool() -> None:
    registry = ChatRuntimePoolRegistry(idle_seconds=3600.0)

    async def build_pool() -> MagicMock:
        pool = MagicMock()
        pool.available_backends = ["claude"]
        pool.close_all = AsyncMock()
        return pool

    pool = await registry.acquire("chat-1", "fp-a", build_pool)
    await registry.release("chat-1")
    pool.close_all.assert_not_called()


@pytest.mark.asyncio
async def test_idle_eviction_closes_stale_pool() -> None:
    registry = ChatRuntimePoolRegistry(idle_seconds=0.01)

    async def build_pool() -> MagicMock:
        pool = MagicMock()
        pool.available_backends = ["claude"]
        pool.close_all = AsyncMock()
        return pool

    pool = await registry.acquire("chat-1", "fp-a", build_pool)
    await registry.release("chat-1")
    await asyncio.sleep(0.02)
    await registry.acquire("chat-2", "fp-a", build_pool)
    pool.close_all.assert_awaited_once()


@pytest.mark.asyncio
async def test_guard_turn_serializes_same_chat() -> None:
    registry = ChatRuntimePoolRegistry()
    order: list[str] = []
    gate = asyncio.Event()
    release = asyncio.Event()

    async def first_turn() -> None:
        async with registry.guard_turn("chat-1"):
            order.append("first_start")
            gate.set()
            await release.wait()
            order.append("first_end")

    async def second_turn() -> None:
        await gate.wait()
        async with registry.guard_turn("chat-1"):
            order.append("second")

    task1 = asyncio.create_task(first_turn())
    await gate.wait()
    task2 = asyncio.create_task(second_turn())
    await asyncio.sleep(0.01)
    assert order == ["first_start"]
    release.set()
    await asyncio.gather(task1, task2)
    assert order == ["first_start", "first_end", "second"]


@pytest.mark.asyncio
async def test_guard_turn_allows_parallel_different_chats() -> None:
    registry = ChatRuntimePoolRegistry()
    order: list[str] = []
    gate_a = asyncio.Event()
    gate_b = asyncio.Event()

    async def turn(chat_id: str, gate: asyncio.Event) -> None:
        async with registry.guard_turn(chat_id):
            order.append(f"{chat_id}_start")
            gate.set()
            await asyncio.sleep(0.02)
            order.append(f"{chat_id}_end")

    task_a = asyncio.create_task(turn("chat-a", gate_a))
    task_b = asyncio.create_task(turn("chat-b", gate_b))
    await asyncio.gather(gate_a.wait(), gate_b.wait())
    await asyncio.gather(task_a, task_b)
    assert "chat-a_start" in order
    assert "chat-b_start" in order
    assert order.index("chat-a_start") < order.index("chat-a_end")
    assert order.index("chat-b_start") < order.index("chat-b_end")


@pytest.mark.asyncio
async def test_acquire_defers_replace_when_turn_in_progress() -> None:
    registry = ChatRuntimePoolRegistry(idle_seconds=3600.0)
    pool = MagicMock()
    pool.available_backends = ["claude"]
    pool.close_all = AsyncMock()
    build_count = 0

    async def build_pool() -> MagicMock:
        nonlocal build_count
        build_count += 1
        return pool

    first = await registry.acquire("chat-1", "fp-a", build_pool)
    release = asyncio.Event()

    async def holding_turn() -> None:
        async with registry.guard_turn("chat-1"):
            await release.wait()

    turn_task = asyncio.create_task(holding_turn())
    await asyncio.sleep(0.01)

    second = await registry.acquire("chat-1", "fp-b", build_pool)
    assert second is first
    pool.close_all.assert_not_called()
    assert build_count == 1

    release.set()
    await turn_task

    third = await registry.acquire("chat-1", "fp-b", build_pool)
    assert third is pool
    pool.close_all.assert_awaited_once()
    assert build_count == 2


@pytest.mark.asyncio
async def test_facade_cancel_does_not_deadlock_during_run_turn() -> None:
    registry = ChatRuntimePoolRegistry()
    entered = asyncio.Event()
    unblock = asyncio.Event()

    async def slow_run_turn(
        name: str,
        prompt: str,
        session_id: str,
        *,
        mode: str = "persistent",
    ):
        entered.set()
        await unblock.wait()
        yield MagicMock()

    pool = MagicMock()
    pool.run_turn = slow_run_turn
    pool.cancel = AsyncMock()

    facade = ChatScopedRuntimePoolFacade(pool, "chat-1", registry)

    async def consume() -> None:
        async for _ in facade.run_turn("claude", "hi", "s1"):
            pass

    task = asyncio.create_task(consume())
    await asyncio.wait_for(entered.wait(), timeout=1.0)
    await asyncio.wait_for(facade.cancel("claude", "s1"), timeout=1.0)
    pool.cancel.assert_awaited_once_with("claude", "s1")
    unblock.set()
    await task


@pytest.mark.asyncio
async def test_guard_turn_noop_for_empty_scope() -> None:
    registry = ChatRuntimePoolRegistry()
    ran = False

    async with registry.guard_turn(None):
        ran = True
    async with registry.guard_turn(""):
        ran = True

    assert ran is True


@pytest.mark.asyncio
async def test_close_chat_tears_down_pool_and_turn_lock() -> None:
    registry = ChatRuntimePoolRegistry(idle_seconds=3600.0)

    async def build_pool() -> MagicMock:
        pool = MagicMock()
        pool.available_backends = ["claude"]
        pool.close_all = AsyncMock()
        return pool

    pool = await registry.acquire("chat-1", "fp-a", build_pool)
    async with registry.guard_turn("chat-1"):
        pass

    await registry.close_chat("chat-1")
    pool.close_all.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_all_continues_after_single_pool_failure() -> None:
    registry = ChatRuntimePoolRegistry(idle_seconds=3600.0)
    good = MagicMock()
    good.available_backends = ["claude"]
    good.close_all = AsyncMock()
    bad = MagicMock()
    bad.available_backends = ["codex"]
    bad.close_all = AsyncMock(side_effect=RuntimeError("boom"))

    build_seq = iter([good, bad])

    async def build_pool() -> MagicMock:
        return next(build_seq)

    await registry.acquire("chat-a", "fp-a", build_pool)
    await registry.acquire("chat-b", "fp-a", build_pool)
    await registry.close_all()
    good.close_all.assert_awaited_once()
    bad.close_all.assert_awaited_once()


@pytest.mark.asyncio
async def test_facade_delegates_properties_and_getattr() -> None:
    registry = ChatRuntimePoolRegistry()
    pool = MagicMock()
    pool.available_backends = ["claude", "codex"]
    pool.get_config = MagicMock(return_value={"name": "claude"})
    pool.start_monitoring = AsyncMock()

    facade = ChatScopedRuntimePoolFacade(pool, "chat-1", registry)
    assert facade.available_backends == ["claude", "codex"]
    assert facade.get_config("claude") == {"name": "claude"}
    assert facade.start_monitoring is pool.start_monitoring
