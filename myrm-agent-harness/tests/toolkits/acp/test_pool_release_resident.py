"""RuntimePool.release_resident: free resident processes, keep per-turn backends and their resume state.

The real-process form of this contract lives in ``test_pool_mock_acp_agent.py`` (ACP process is
released and respawned) and ``test_pool_cli_resume.py`` (CLI ``--resume`` id survives).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest

from myrm_agent_harness.toolkits.acp.runtime.pool import RuntimePool
from myrm_agent_harness.toolkits.acp.types import (
    BackendCapabilities,
    BackendInfo,
    RuntimeConfig,
    RuntimeEvent,
)

_POOL_FACTORY = "myrm_agent_harness.toolkits.acp.runtime.pool._create_runtime"


class _FakeBackend:
    name = "fake"
    capabilities = BackendCapabilities()
    is_alive = True

    def __init__(self, *, close_error: Exception | None = None) -> None:
        self.closed = False
        self._close_error = close_error

    async def run_turn(self, prompt: str, session_id: str, *, mcp_servers=None) -> AsyncIterator[RuntimeEvent]:
        return
        yield  # pragma: no cover - makes this an async generator

    async def cancel(self, session_id: str) -> None:
        return None

    async def resume(self, session_id: str) -> bool:
        return False

    async def get_info(self) -> BackendInfo:
        return BackendInfo(name=self.name)

    async def close(self) -> None:
        self.closed = True
        if self._close_error is not None:
            raise self._close_error


class _Factory:
    """Stands in for ``_create_runtime`` and remembers every backend it handed out, per name."""

    def __init__(self, *, failing_close: frozenset[str] = frozenset()) -> None:
        self.created: dict[str, list[_FakeBackend]] = {}
        self._failing_close = failing_close

    def __call__(self, name: str, config: RuntimeConfig, *, event_bus=None) -> _FakeBackend:
        error = RuntimeError("close failed") if name in self._failing_close else None
        backend = _FakeBackend(close_error=error)
        self.created.setdefault(name, []).append(backend)
        return backend


def _pool(**backend_types: str) -> RuntimePool:
    pool = RuntimePool()
    for name, backend_type in backend_types.items():
        pool.register(name, RuntimeConfig(backend_type=backend_type, command=name))  # type: ignore[arg-type]
    return pool


@pytest.mark.asyncio
async def test_release_resident_closes_acp_backends_and_keeps_cli_backends() -> None:
    pool = _pool(resident="acp", per_turn="cli")
    factory = _Factory()

    with patch(_POOL_FACTORY, factory):
        resident = pool.get("resident")
        per_turn = pool.get("per_turn")
        await pool.release_resident()

        assert resident.closed
        assert not per_turn.closed
        assert pool.get("per_turn") is per_turn
        # The released ACP backend is recreated lazily by the next turn.
        assert pool.get("resident") is not resident

    assert len(factory.created["resident"]) == 2
    assert len(factory.created["per_turn"]) == 1


@pytest.mark.asyncio
async def test_release_resident_leaves_a_cli_only_pool_untouched() -> None:
    pool = _pool(first="cli", second="cli")
    factory = _Factory()

    with patch(_POOL_FACTORY, factory):
        backends = [pool.get("first"), pool.get("second")]
        await pool.release_resident()

        assert not any(backend.closed for backend in backends)
        assert [pool.get("first"), pool.get("second")] == backends


@pytest.mark.asyncio
async def test_release_resident_is_a_noop_before_any_backend_exists() -> None:
    await _pool(resident="acp").release_resident()


@pytest.mark.asyncio
async def test_release_resident_swallows_a_failing_close_and_still_drops_the_backend() -> None:
    pool = _pool(resident="acp")
    factory = _Factory(failing_close=frozenset({"resident"}))

    with patch(_POOL_FACTORY, factory):
        broken = pool.get("resident")
        await pool.release_resident()

        assert broken.closed
        assert pool.get("resident") is not broken
