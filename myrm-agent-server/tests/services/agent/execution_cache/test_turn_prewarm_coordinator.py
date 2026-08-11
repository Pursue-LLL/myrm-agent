"""Tests for TurnPrewarmCoordinator."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.execution_cache.prewarm.coordinator import TurnPrewarmCoordinator
from app.services.agent.execution_cache.registry import get_execution_cache
from app.services.agent.execution_cache.types import BuiltExecutionUnit


@pytest.fixture(autouse=True)
async def _reset_execution_cache_singleton() -> None:
    await get_execution_cache().close_all()
    yield
    await get_execution_cache().close_all()


def _make_unit() -> BuiltExecutionUnit:
    skill_agent = MagicMock()
    skill_agent.close = AsyncMock()
    return BuiltExecutionUnit(skill_agent=skill_agent)


def _make_params(*, chat_id: str = "c-test", agent_id: str | None = "default") -> MagicMock:
    params = MagicMock()
    params.chat_id = chat_id
    params.agent_id = agent_id
    params.incognito_mode = False
    params.enable_memory = True
    params.embedding_config = object()
    return params


@pytest.mark.asyncio
async def test_coalesced_acquire_deduplicates_parallel_builds() -> None:
    coordinator = TurnPrewarmCoordinator()
    scope_key = "c-test:default"
    fingerprint = "fp-a"
    build_count = 0
    started = asyncio.Event()

    async def build_unit() -> BuiltExecutionUnit:
        nonlocal build_count
        build_count += 1
        started.set()
        await asyncio.sleep(0.05)
        return _make_unit()

    task_a = asyncio.create_task(
        coordinator.coalesced_acquire(scope_key, fingerprint, build_unit),
    )
    task_b = asyncio.create_task(
        coordinator.coalesced_acquire(scope_key, fingerprint, build_unit),
    )
    first, second = await asyncio.gather(task_a, task_b)

    assert first is second
    assert build_count == 1
    assert await get_execution_cache().is_warm(scope_key, fingerprint)


@pytest.mark.asyncio
async def test_join_for_turn_uses_brief_cache_when_ready() -> None:
    coordinator = TurnPrewarmCoordinator()
    scope_key = "c-test:default"
    fingerprint = "fp-b"
    preview = {"snapshot_id": "snap-1", "items": []}
    snapshot = {"snapshot_id": "snap-1"}
    coordinator._brief_cache.put(scope_key, fingerprint, preview, snapshot)

    params = _make_params()
    wrapper = MagicMock()
    wrapper.agent_id = "default"

    with patch(
        "app.services.agent.execution_cache.prewarm.coordinator.AgentFactory.create_general_agent",
        return_value=wrapper,
    ), patch(
        "app.services.agent.execution_cache.prewarm.coordinator.compute_execution_fingerprint",
        return_value=fingerprint,
    ), patch(
        "app.services.agent.execution_cache.prewarm.coordinator.build_execution_scope_key",
        return_value=scope_key,
    ), patch.object(
        coordinator,
        "_should_warm_agent",
        return_value=False,
    ):
        result = await coordinator.join_for_turn(params)

    assert result.preview == preview
    assert result.snapshot == snapshot
    assert result.brief_status == {"state": "ready", "source": "preflight"}


@pytest.mark.asyncio
async def test_cancel_scope_clears_inflight_and_brief_cache() -> None:
    coordinator = TurnPrewarmCoordinator()
    scope_key = "c-test:default"
    fingerprint = "fp-c"
    coordinator._brief_cache.put(scope_key, fingerprint, {"snapshot_id": "x"}, {"snapshot_id": "x"})

    async def slow_build() -> BuiltExecutionUnit:
        await asyncio.sleep(5)
        return _make_unit()

    task = asyncio.create_task(
        coordinator.coalesced_acquire(scope_key, fingerprint, slow_build),
    )
    await asyncio.sleep(0.01)
    await coordinator.cancel_scope("c-test", "default")
    assert coordinator._brief_cache.get(scope_key, fingerprint) is None
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_cancel_scope_clears_agent_ready_timestamp() -> None:
    coordinator = TurnPrewarmCoordinator()
    coordinator._agent_ready_at["c-test:default:fp-c"] = 1.0

    await coordinator.cancel_scope("c-test", "default")

    assert coordinator._agent_ready_at == {}


def test_prune_agent_ready_timestamps_removes_expired_entries() -> None:
    coordinator = TurnPrewarmCoordinator()
    coordinator._agent_ready_at["expired"] = 1.0
    coordinator._brief_cache.put("c-expired:default", "fp", {}, {})
    coordinator._brief_cache._ttl_seconds = 0.0

    coordinator._prune_agent_ready_at()

    assert coordinator._agent_ready_at == {}
    assert coordinator._brief_cache.get("c-expired:default", "fp") is None
