"""Tests for chat-scoped execution cache registry."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.agent.execution_cache.registry import (
    ChatAgentExecutionCache,
    close_execution_cache_for_chat_all_agents,
    get_execution_cache,
)
from app.services.agent.execution_cache.types import BuiltExecutionUnit


@pytest.fixture(autouse=True)
async def _reset_execution_cache_singleton() -> None:
    await get_execution_cache().close_all()
    yield
    await get_execution_cache().close_all()


def _make_unit(name: str = "unit") -> BuiltExecutionUnit:
    skill_agent = MagicMock()
    skill_agent.close = AsyncMock()
    return BuiltExecutionUnit(skill_agent=skill_agent)


@pytest.mark.asyncio
async def test_acquire_reuses_unit_for_same_scope_and_fingerprint() -> None:
    registry = ChatAgentExecutionCache(idle_seconds=3600.0)
    build_count = 0

    async def build_unit() -> BuiltExecutionUnit:
        nonlocal build_count
        build_count += 1
        return _make_unit()

    first = await registry.acquire("chat-1:default", "fp-a", build_unit)
    second = await registry.acquire("chat-1:default", "fp-a", build_unit)

    assert first is second
    assert build_count == 1
    first.skill_agent.close.assert_not_called()


@pytest.mark.asyncio
async def test_acquire_replaces_unit_when_fingerprint_changes() -> None:
    registry = ChatAgentExecutionCache(idle_seconds=3600.0)
    units: list[BuiltExecutionUnit] = []

    async def build_unit() -> BuiltExecutionUnit:
        unit = _make_unit()
        units.append(unit)
        return unit

    first = await registry.acquire("chat-1:default", "fp-a", build_unit)
    second = await registry.acquire("chat-1:default", "fp-b", build_unit)

    assert first is not second
    assert len(units) == 2
    first.skill_agent.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_release_does_not_teardown_unit() -> None:
    registry = ChatAgentExecutionCache(idle_seconds=3600.0)

    async def build_unit() -> BuiltExecutionUnit:
        return _make_unit()

    unit = await registry.acquire("chat-1:default", "fp-a", build_unit)
    await registry.release("chat-1:default")
    unit.skill_agent.close.assert_not_called()


@pytest.mark.asyncio
async def test_close_scopes_for_chat_all_agents() -> None:
    registry = ChatAgentExecutionCache(idle_seconds=3600.0)
    build_count = 0

    async def build_unit() -> BuiltExecutionUnit:
        nonlocal build_count
        build_count += 1
        return _make_unit()

    await registry.acquire("chat-1:agent-a", "fp-a", build_unit)
    await registry.acquire("chat-1:agent-b", "fp-a", build_unit)
    await registry.acquire("chat-2:default", "fp-a", build_unit)
    assert build_count == 3

    await registry.close_scopes_for_chat("chat-1")

    await registry.acquire("chat-2:default", "fp-a", build_unit)
    assert build_count == 3
    await registry.acquire("chat-1:agent-a", "fp-a", build_unit)
    assert build_count == 4


@pytest.mark.asyncio
async def test_close_execution_cache_for_chat_all_agents_noop_on_empty() -> None:
    await close_execution_cache_for_chat_all_agents(None)
    await close_execution_cache_for_chat_all_agents("")


@pytest.mark.asyncio
async def test_guard_turn_serializes_same_scope() -> None:
    registry = ChatAgentExecutionCache()
    order: list[str] = []
    gate = asyncio.Event()
    release = asyncio.Event()

    async def first_turn() -> None:
        async with registry.guard_turn("chat-1:default"):
            order.append("first_start")
            gate.set()
            await release.wait()
            order.append("first_end")

    async def second_turn() -> None:
        await gate.wait()
        async with registry.guard_turn("chat-1:default"):
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
async def test_refresh_unit_updates_cached_entry() -> None:
    registry = ChatAgentExecutionCache(idle_seconds=3600.0)

    async def build_unit() -> BuiltExecutionUnit:
        return _make_unit("original")

    first = await registry.acquire("chat-1:default", "fp-a", build_unit)
    refreshed = _make_unit("refreshed")
    await registry.refresh_unit("chat-1:default", refreshed)
    second = await registry.acquire("chat-1:default", "fp-a", build_unit)

    assert second is refreshed
    assert second is not first
    first.skill_agent.close.assert_not_called()
