"""Tests for chat-scoped RuntimePool registry."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

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


async def _build_mock_pool() -> MagicMock:
    pool = MagicMock()
    pool.available_backends = ["claude"]
    pool.close_all = AsyncMock()
    return pool


async def _unexpected_build() -> MagicMock:
    raise AssertionError("the existing pool must be reused, not rebuilt")


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
async def test_idle_eviction_skips_pool_with_turn_in_flight() -> None:
    """A delegation that outlives the idle window keeps its pool and its turn lock."""
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
    """A turn longer than the idle window must not get its pool evicted the moment it ends."""
    registry = ChatRuntimePoolRegistry(idle_seconds=0.05)
    pool = await registry.acquire("chat-1", "fp-a", _build_mock_pool)

    async with registry.guard_turn("chat-1"):
        await asyncio.sleep(0.08)
    await registry.acquire("chat-2", "fp-a", _build_mock_pool)
    pool.close_all.assert_not_called()

    await asyncio.sleep(0.08)
    await registry.acquire("chat-3", "fp-a", _build_mock_pool)
    pool.close_all.assert_awaited_once()


@pytest.mark.asyncio
async def test_guard_turn_restarts_idle_clock_when_turn_fails() -> None:
    registry = ChatRuntimePoolRegistry(idle_seconds=0.05)
    pool = await registry.acquire("chat-1", "fp-a", _build_mock_pool)

    with pytest.raises(RuntimeError, match="delegation failed"):
        async with registry.guard_turn("chat-1"):
            await asyncio.sleep(0.08)
            raise RuntimeError("delegation failed")
    await registry.acquire("chat-2", "fp-a", _build_mock_pool)

    pool.close_all.assert_not_called()


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
        mcp_servers: list | None = None,
    ):
        entered.set()
        await unblock.wait()
        yield MagicMock()

    pool = MagicMock()
    pool.run_turn = slow_run_turn
    pool.cancel = AsyncMock()

    async def build_pool() -> MagicMock:
        return pool

    await registry.acquire("chat-1", "fp-a", build_pool)
    facade = ChatScopedRuntimePoolFacade(pool, "chat-1", registry, "fp-a")

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
async def test_facade_exposes_only_the_delegation_surface() -> None:
    registry = ChatRuntimePoolRegistry()
    pool = MagicMock()
    pool.available_backends = ["claude", "codex"]
    pool.get_config = MagicMock(return_value={"name": "claude"})

    facade = ChatScopedRuntimePoolFacade(pool, "chat-1", registry, "fp-a")
    assert facade.available_backends == ["claude", "codex"]
    assert facade.get_config("claude") == {"name": "claude"}
    # Anything beyond the delegation surface would reach the pool without taking the chat's turn lock.
    assert not hasattr(facade, "prompt")


@pytest.mark.asyncio
async def test_close_external_agent_pool_for_chat_noop_on_empty() -> None:
    from app.services.external_agents.runtime_pool_registry import (
        close_external_agent_pool_for_chat,
    )

    await close_external_agent_pool_for_chat(None)
    await close_external_agent_pool_for_chat("")
    await close_external_agent_pool_for_chat("   ")


@pytest.mark.asyncio
async def test_close_external_agent_pool_for_chat_swallows_registry_errors() -> None:
    from app.services.external_agents.runtime_pool_registry import (
        close_external_agent_pool_for_chat,
    )

    registry = MagicMock()
    registry.close_chat = AsyncMock(side_effect=RuntimeError("boom"))
    with patch(
        "app.services.external_agents.runtime_pool_registry.get_chat_runtime_pool_registry",
        return_value=registry,
    ):
        await close_external_agent_pool_for_chat("chat-err")
    registry.close_chat.assert_awaited_once_with("chat-err")


def _build_turn_pool(label: str, ran_on: list[str]) -> MagicMock:
    """A pool whose run_turn records which pool served the turn."""

    async def run_turn(name: str, prompt: str, session_id: str, *, mode: str = "persistent", mcp_servers=None):
        ran_on.append(label)
        yield MagicMock()

    pool = MagicMock()
    pool.available_backends = ["claude"]
    pool.run_turn = run_turn
    pool.cancel = AsyncMock()
    pool.close_all = AsyncMock()
    return pool


async def _evict_chat_one(registry: ChatRuntimePoolRegistry, pool: MagicMock) -> None:
    """Acquire chat-1's pool, let it go idle, and have another chat's acquire evict it."""

    async def build_pool() -> MagicMock:
        return pool

    await registry.acquire("chat-1", "fp-a", build_pool)
    await asyncio.sleep(0.03)
    await registry.acquire("chat-2", "fp-a", _build_mock_pool)
    pool.close_all.assert_awaited_once()
    assert "chat-1" not in registry._entries


@pytest.mark.asyncio
async def test_ensure_tracked_fast_path_does_not_wait_for_registry_lock() -> None:
    """A turn on a registered pool must not queue behind another chat's slow pool close."""
    registry = ChatRuntimePoolRegistry(idle_seconds=3600.0)
    pool = _build_turn_pool("p", [])

    async def build_pool() -> MagicMock:
        return pool

    await registry.acquire("chat-1", "fp-a", build_pool)
    async with registry._lock:
        tracked = await asyncio.wait_for(registry.ensure_tracked("chat-1", "fp-a", pool), timeout=0.5)

    assert tracked is pool


@pytest.mark.asyncio
async def test_ensure_tracked_readopts_evicted_pool_so_shutdown_closes_it() -> None:
    """A closed pool revives its backends on the next turn; they must stay reachable by close_all."""
    registry = ChatRuntimePoolRegistry(idle_seconds=0.01)
    pool = _build_turn_pool("p", [])
    await _evict_chat_one(registry, pool)

    tracked = await registry.ensure_tracked("chat-1", "fp-a", pool)

    assert tracked is pool
    assert registry._entries["chat-1"].pool is pool
    await registry.close_all()
    assert pool.close_all.await_count == 2


@pytest.mark.asyncio
async def test_ensure_tracked_prefers_the_registered_pool_over_a_stale_one() -> None:
    registry = ChatRuntimePoolRegistry(idle_seconds=3600.0)
    current = _build_turn_pool("current", [])
    stale = _build_turn_pool("stale", [])

    async def build_pool() -> MagicMock:
        return current

    await registry.acquire("chat-1", "fp-a", build_pool)

    assert await registry.ensure_tracked("chat-1", "fp-a", stale) is current


@pytest.mark.asyncio
async def test_facade_run_turn_readopts_pool_evicted_while_the_unit_stayed_cached() -> None:
    registry = ChatRuntimePoolRegistry(idle_seconds=0.01)
    ran_on: list[str] = []
    pool = _build_turn_pool("p", ran_on)
    facade = ChatScopedRuntimePoolFacade(pool, "chat-1", registry, "fp-a")
    await _evict_chat_one(registry, pool)

    async for _ in facade.run_turn("claude", "hi", "s1"):
        pass

    assert ran_on == ["p"]
    assert registry._entries["chat-1"].pool is pool
    await registry.close_all()
    assert pool.close_all.await_count == 2


@pytest.mark.asyncio
async def test_facade_follows_the_registered_pool_for_turns_and_cancel() -> None:
    registry = ChatRuntimePoolRegistry(idle_seconds=3600.0)
    ran_on: list[str] = []
    current = _build_turn_pool("current", ran_on)
    stale = _build_turn_pool("stale", ran_on)

    async def build_pool() -> MagicMock:
        return current

    await registry.acquire("chat-1", "fp-a", build_pool)
    facade = ChatScopedRuntimePoolFacade(stale, "chat-1", registry, "fp-a")

    async for _ in facade.run_turn("claude", "hi", "s1"):
        pass
    await facade.cancel("claude", "s1")

    assert ran_on == ["current"]
    current.cancel.assert_awaited_once_with("claude", "s1")
    stale.cancel.assert_not_called()
