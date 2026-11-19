"""McpWarmup: serve a server's surface from its cached tool table, start its session later, keep the cache true.

[INPUT]
- myrm_agent_harness.toolkits.mcp.warmup (POS: unit under test)
- myrm_agent_harness.toolkits.mcp.tool_table_store (POS: the cache the warm-up reads and writes)
- tests.support.mcp_warmup_doubles (POS: the pool double and the tool builders)

[OUTPUT]
- Unit tests for serving rules, background verification, cache refresh and drop, and the settle barrier.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import threading
from pathlib import Path
from types import ModuleType

import pytest

from myrm_agent_harness.toolkits.mcp.structured_tool import SafeStructuredTool
from myrm_agent_harness.toolkits.mcp.tool_table import ServerSurface, encode_table
from myrm_agent_harness.toolkits.mcp.tool_table_store import ToolTableStore
from myrm_agent_harness.toolkits.mcp.warmup import McpWarmup
from tests.support.mcp_warmup_doubles import FakeConnection, FakePool, config, live_tools, table_of

_LOGGER = "myrm_agent_harness.toolkits.mcp.warmup"
_NO_THRESHOLD = 0


@pytest.fixture
def store(tmp_path: Path) -> ToolTableStore:
    return ToolTableStore(tmp_path / "tables")


@pytest.fixture
def pool() -> FakePool:
    return FakePool()


async def _serve(warmup: McpWarmup, pool: FakePool, threshold: int = _NO_THRESHOLD) -> dict[str, ServerSurface]:
    return await warmup.serve(pool, [config()], threshold=threshold)


async def test_nothing_is_served_without_a_cached_table(store: ToolTableStore, pool: FakePool) -> None:
    warmup = McpWarmup(store)

    assert await _serve(warmup, pool) == {}
    assert not warmup.has_jobs


async def test_a_cached_server_is_served_and_its_session_waits_for_start(store: ToolTableStore, pool: FakePool) -> None:
    store.save("hash-demo", table_of("a", "b", instructions="Use a first."))
    warmup = McpWarmup(store)

    served = await _serve(warmup, pool)

    assert [tool.name for tool in served["demo"].tools] == ["a", "b"]
    assert served["demo"].instructions == "Use a first."
    assert warmup.has_jobs
    assert pool.asked == []


async def test_a_server_the_model_gets_as_direct_tools_is_not_served(store: ToolTableStore, pool: FakePool) -> None:
    store.save("hash-demo", table_of("a"))
    warmup = McpWarmup(store)

    assert await _serve(warmup, pool, threshold=10**9) == {}
    assert not warmup.has_jobs


async def test_a_server_the_pool_already_holds_is_not_served(store: ToolTableStore, pool: FakePool) -> None:
    store.save("hash-demo", table_of("a"))
    pool.pooled.add("demo")
    warmup = McpWarmup(store)

    assert await _serve(warmup, pool) == {}
    assert not warmup.has_jobs


async def test_start_runs_each_session_once(store: ToolTableStore, pool: FakePool) -> None:
    store.save("hash-demo", table_of("a"))
    pool.live["demo"] = FakeConnection("demo", live_tools("a"))
    warmup = McpWarmup(store)
    await _serve(warmup, pool)

    warmup.start()
    warmup.start()
    await warmup.settle()

    assert pool.asked == ["demo"]


async def test_the_sdk_is_imported_off_the_event_loop_before_the_session_is_asked_for(
    store: ToolTableStore, pool: FakePool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The import is hundreds of milliseconds of CPU: on the loop it would hold up the request being sent."""
    store.save("hash-demo", table_of("a"))
    pool.live["demo"] = FakeConnection("demo", live_tools("a"))
    imports: list[tuple[int, list[str]]] = []
    real_import_module = importlib.import_module

    def import_module(name: str, package: str | None = None) -> ModuleType:
        if name == "mcp":
            imports.append((threading.get_ident(), list(pool.asked)))
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", import_module)
    warmup = McpWarmup(store)
    await _serve(warmup, pool)

    warmup.start()
    await warmup.settle()

    assert len(imports) == 1
    importing_thread, asked_at_import = imports[0]
    assert importing_thread != threading.get_ident()
    assert asked_at_import == []
    assert pool.asked == ["demo"]


async def test_a_missing_sdk_is_reported_like_a_session_that_cannot_start(
    store: ToolTableStore, pool: FakePool, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    store.save("hash-demo", table_of("a"))
    warmup = McpWarmup(store)
    await _serve(warmup, pool)
    real_import_module = importlib.import_module

    def import_module(name: str, package: str | None = None) -> ModuleType:
        if name == "mcp":
            raise ModuleNotFoundError("No module named 'mcp'")
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", import_module)

    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        warmup.start()
        await warmup.settle()

    assert pool.asked == []
    assert store.load("hash-demo") is None
    assert "failed to start after its cached tool table was served" in caplog.text


async def test_an_unchanged_surface_leaves_the_cache_alone(
    store: ToolTableStore, pool: FakePool, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.save("hash-demo", table_of("a", "b"))
    pool.live["demo"] = FakeConnection("demo", live_tools("a", "b"))
    warmup = McpWarmup(store)
    await _serve(warmup, pool)
    monkeypatch.setattr(store, "save", lambda *_: pytest.fail("an unchanged surface must not be written"))
    monkeypatch.setattr(store, "discard", lambda *_: pytest.fail("a reachable server must keep its entry"))

    warmup.start()
    await warmup.settle()


async def test_a_changed_surface_replaces_the_entry_for_the_next_run(
    store: ToolTableStore, pool: FakePool, caplog: pytest.LogCaptureFixture
) -> None:
    store.save("hash-demo", table_of("a"))
    pool.live["demo"] = FakeConnection("demo", live_tools("a", "added"), "New instructions.")
    warmup = McpWarmup(store)
    served = await _serve(warmup, pool)

    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        warmup.start()
        await warmup.settle()

    stored = store.load("hash-demo")
    assert stored is not None
    assert [tool.name for tool in stored.tools] == ["a", "added"]
    assert stored.instructions == "New instructions."
    assert [tool.name for tool in served["demo"].tools] == ["a"]
    assert "tools changed since they were cached" in caplog.text


async def test_a_reordered_surface_counts_as_changed(store: ToolTableStore, pool: FakePool) -> None:
    store.save("hash-demo", table_of("a", "b"))
    pool.live["demo"] = FakeConnection("demo", live_tools("b", "a"))
    warmup = McpWarmup(store)
    await _serve(warmup, pool)

    warmup.start()
    await warmup.settle()

    stored = store.load("hash-demo")
    assert stored is not None
    assert [tool.name for tool in stored.tools] == ["b", "a"]


async def test_a_server_that_fails_to_start_loses_its_entry(
    store: ToolTableStore, pool: FakePool, caplog: pytest.LogCaptureFixture
) -> None:
    store.save("hash-demo", table_of("a"))
    pool.failure = RuntimeError("All MCP servers failed to start: boom")
    warmup = McpWarmup(store)
    await _serve(warmup, pool)

    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        warmup.start()
        await warmup.settle()

    assert store.load("hash-demo") is None
    assert "failed to start after its cached tool table was served" in caplog.text


async def test_a_live_surface_a_table_cannot_carry_drops_the_entry(store: ToolTableStore, pool: FakePool) -> None:
    store.save("hash-demo", table_of("a"))
    odd = SafeStructuredTool(
        name="a",
        description="d",
        args_schema={"type": "object", "default": {1, 2}},
        coroutine=lambda **_: asyncio.sleep(0),
    )
    pool.live["demo"] = FakeConnection("demo", [odd])
    warmup = McpWarmup(store)
    await _serve(warmup, pool)

    warmup.start()
    await warmup.settle()

    assert store.load("hash-demo") is None


async def test_settle_waits_for_a_session_in_progress_and_survives_a_cancelled_caller(
    store: ToolTableStore, pool: FakePool
) -> None:
    store.save("hash-demo", table_of("a"))
    pool.live["demo"] = FakeConnection("demo", live_tools("a"))
    pool.gate = asyncio.Event()
    warmup = McpWarmup(store)
    await _serve(warmup, pool)
    warmup.start()

    waiter = asyncio.create_task(warmup.settle())
    await asyncio.sleep(0.05)
    assert not waiter.done()

    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert warmup._inflight
    assert all(not task.cancelled() for task in warmup._inflight)

    pool.gate.set()
    await asyncio.wait_for(warmup.settle(), timeout=5)
    assert not warmup._inflight


async def test_settle_returns_at_once_when_nothing_is_in_flight(store: ToolTableStore) -> None:
    await asyncio.wait_for(McpWarmup(store).settle(), timeout=1)


def test_settle_does_not_wait_for_work_of_another_event_loop(store: ToolTableStore) -> None:
    other = asyncio.new_event_loop()
    thread = threading.Thread(target=other.run_forever, daemon=True)
    thread.start()

    async def _wait_forever() -> None:
        await asyncio.Event().wait()

    async def _spawn_forever() -> asyncio.Task[None]:
        return asyncio.create_task(_wait_forever())

    foreign = asyncio.run_coroutine_threadsafe(_spawn_forever(), other).result(timeout=5)
    try:
        warmup = McpWarmup(store)
        warmup._inflight.add(foreign)

        asyncio.run(asyncio.wait_for(warmup.settle(), timeout=1))
    finally:
        other.call_soon_threadsafe(foreign.cancel)
        other.call_soon_threadsafe(other.stop)
        thread.join(timeout=5)
        other.close()


async def test_remember_keeps_a_live_surface_for_the_next_cold_start(store: ToolTableStore, pool: FakePool) -> None:
    warmup = McpWarmup(store)

    warmup.remember(pool, config(), ServerSurface(tools=tuple(live_tools("a", "b")), instructions="Hi."))
    await warmup.settle()

    stored = store.load("hash-demo")
    assert stored is not None
    assert encode_table(stored) == encode_table(table_of("a", "b", instructions="Hi."))


async def test_remember_skips_a_surface_a_table_cannot_carry(store: ToolTableStore, pool: FakePool) -> None:
    warmup = McpWarmup(store)

    warmup.remember(pool, config(), ServerSurface(tools=(), instructions=None))
    await warmup.settle()

    assert store.load("hash-demo") is None


def _broken(*_: object) -> None:
    raise OSError("disk is read-only")


async def test_a_failing_disk_never_breaks_remembering_or_refreshing(
    store: ToolTableStore, pool: FakePool, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    store.save("hash-demo", table_of("a"))
    pool.live["demo"] = FakeConnection("demo", live_tools("a", "added"))
    warmup = McpWarmup(store)
    await _serve(warmup, pool)
    monkeypatch.setattr(store, "save", _broken)

    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        warmup.remember(pool, config("other"), ServerSurface(tools=tuple(live_tools("x")), instructions=None))
        warmup.start()
        await warmup.settle()

    assert caplog.text.count("could not be cached") == 2


async def test_an_unexpected_failure_in_the_background_is_logged_and_never_reaches_the_waiter(
    store: ToolTableStore, pool: FakePool, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def explode(surface: ServerSurface) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("myrm_agent_harness.toolkits.mcp.warmup.capture_table", explode)
    warmup = McpWarmup(store)

    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        warmup.remember(pool, config(), ServerSurface(tools=tuple(live_tools("a")), instructions=None))
        await warmup.settle()

    assert "mcp-cache-demo' failed: boom" in caplog.text
    assert not warmup._inflight


async def test_a_failing_disk_never_breaks_dropping_an_entry(
    store: ToolTableStore, pool: FakePool, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    store.save("hash-demo", table_of("a"))
    pool.failure = RuntimeError("down")
    warmup = McpWarmup(store)
    await _serve(warmup, pool)
    monkeypatch.setattr(store, "discard", _broken)

    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        warmup.start()
        await warmup.settle()

    assert "could not be dropped" in caplog.text
