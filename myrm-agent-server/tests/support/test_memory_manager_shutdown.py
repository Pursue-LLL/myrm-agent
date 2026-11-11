"""Tests for the bounded shutdown of the cached memory managers."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import cast

import aiosqlite
import pytest
from myrm_agent_harness.toolkits.memory import MemoryManager

from app.core.memory.adapters import setup
from tests.support.memory_manager_shutdown import shutdown_cached_memory_managers_bounded

# Keeps a connection's worker thread inside one query long enough for the loop that asked for it to close first.
_LONG_QUERY = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 4000000) SELECT count(*) FROM c"
_CLOSE_BOUND_SECONDS = 0.5
# The bound plus a few cancel rounds; a close that is never given up on takes forever, far beyond this.
_RETURN_WITHIN_SECONDS = 10.0
_NO_WARNING_BOUND_SECONDS = 60.0
_GIVE_UP_MESSAGE = "did not close within"


class _ConnectionManager:
    """Stands in for a cached MemoryManager whose close goes through one aiosqlite connection."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._connection = connection
        self.closed = False

    async def close(self) -> None:
        await self._connection.close()
        self.closed = True


@pytest.fixture
def manager_cache(monkeypatch: pytest.MonkeyPatch) -> dict[tuple[object, ...], MemoryManager]:
    """An empty cache, so the shutdown closes only what the test put there and not another test's leftovers."""
    cache: dict[tuple[object, ...], MemoryManager] = {}
    monkeypatch.setattr(setup, "_memory_manager_cache", cache)
    return cache


def _orphaned_connection() -> aiosqlite.Connection:
    """Open a connection, then close its event loop while the worker thread is still inside a query.

    The worker cannot hand the query's result to the closed loop, so it dies, and the connection never answers again.
    """
    threads_before = set(threading.enumerate())

    async def open_and_leave_a_query_running() -> aiosqlite.Connection:
        connection = await aiosqlite.connect(":memory:")
        asyncio.ensure_future(connection.execute(_LONG_QUERY))
        await asyncio.sleep(0.05)
        return connection

    connection = asyncio.run(open_and_leave_a_query_running())
    workers = [t for t in threading.enumerate() if t not in threads_before and "_connection_worker_thread" in t.name]
    assert len(workers) == 1
    workers[0].join(timeout=_RETURN_WITHIN_SECONDS)
    assert not workers[0].is_alive(), "the scenario no longer kills the worker, so it no longer tests the bound"
    return connection


@pytest.mark.timeout(60)
def test_a_connection_that_lost_its_worker_does_not_hold_the_shutdown(
    manager_cache: dict[tuple[object, ...], MemoryManager],
    caplog: pytest.LogCaptureFixture,
) -> None:
    manager_cache[("orphaned",)] = cast("MemoryManager", _ConnectionManager(_orphaned_connection()))
    started = time.monotonic()

    with caplog.at_level(logging.WARNING):
        asyncio.run(shutdown_cached_memory_managers_bounded(timeout=_CLOSE_BOUND_SECONDS))

    assert time.monotonic() - started < _RETURN_WITHIN_SECONDS
    assert _GIVE_UP_MESSAGE in caplog.text
    assert not manager_cache


@pytest.mark.timeout(60)
def test_a_healthy_manager_is_closed_without_a_warning(
    manager_cache: dict[tuple[object, ...], MemoryManager],
    caplog: pytest.LogCaptureFixture,
) -> None:
    managers: list[_ConnectionManager] = []

    async def close_a_healthy_manager() -> None:
        manager = _ConnectionManager(await aiosqlite.connect(":memory:"))
        managers.append(manager)
        manager_cache[("healthy",)] = cast("MemoryManager", manager)
        await shutdown_cached_memory_managers_bounded(timeout=_NO_WARNING_BOUND_SECONDS)

    with caplog.at_level(logging.WARNING):
        asyncio.run(close_a_healthy_manager())

    assert managers[0].closed
    assert _GIVE_UP_MESSAGE not in caplog.text


@pytest.mark.timeout(60)
@pytest.mark.usefixtures("manager_cache")
def test_a_failure_that_is_not_a_hang_still_reaches_the_caller(monkeypatch: pytest.MonkeyPatch) -> None:
    async def failing_cascade_shutdown() -> None:
        raise RuntimeError("cascade shutdown failed")

    monkeypatch.setattr("app.core.memory.adapters.cascade.shutdown_cascade_manager", failing_cascade_shutdown)

    with pytest.raises(RuntimeError, match="cascade shutdown failed"):
        asyncio.run(shutdown_cached_memory_managers_bounded(timeout=_NO_WARNING_BOUND_SECONDS))
