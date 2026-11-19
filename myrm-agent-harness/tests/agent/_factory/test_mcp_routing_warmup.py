"""route_mcp_servers with a warm-up: Skill-path servers come from their cached tool table, the rest route as always.

[INPUT]
- myrm_agent_harness.agent._factory.mcp_routing (POS: unit under test)
- myrm_agent_harness.toolkits.mcp.warmup (POS: serves and remembers the tool tables)
- tests.support.mcp_warmup_doubles (POS: the pool double and the tool builders)

[OUTPUT]
- Tests that a warm start builds the very Skill surface a cold start builds without waiting for a session, and that
  direct servers, forced-direct mode and pooled servers never take the cached path.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.agent._factory import mcp_routing
from myrm_agent_harness.agent._factory.mcp_routing import route_mcp_servers
from myrm_agent_harness.agent._factory.mcp_surface import MCPSurfaceMode
from myrm_agent_harness.toolkits.mcp.config import MCPConfig
from myrm_agent_harness.toolkits.mcp.tool_table_store import ToolTableStore
from myrm_agent_harness.toolkits.mcp.warmup import McpWarmup
from tests.support.mcp_warmup_doubles import FakeConnection, FakePool, config, live_tools, table_of

_HEAVY = 2_000
"""Description padding that puts a server far above the routing threshold of the tests that use it."""

_THRESHOLD = 200


@pytest.fixture
def store(tmp_path: Path) -> ToolTableStore:
    return ToolTableStore(tmp_path / "tables")


@pytest.fixture
def pool(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakePool]:
    fake = FakePool()
    monkeypatch.setattr(mcp_routing, "compute_direct_threshold", lambda *_: _THRESHOLD)
    with (
        patch(
            "myrm_agent_harness.toolkits.mcp.connection_manager.get_mcp_connection_manager",
            AsyncMock(return_value=fake),
        ),
        patch("myrm_agent_harness.agent.skills.runtime.registry.skill_registry.register"),
    ):
        yield fake


def _expose(pool: FakePool, name: str, *, heavy: bool) -> None:
    tools = live_tools(f"mcp__{name}__a", f"mcp__{name}__b", schema_chars=_HEAVY if heavy else 0)
    pool.live[name] = FakeConnection(name, tools, f"{name} instructions.")


async def _route(
    pool: FakePool,
    warmup: McpWarmup | None,
    configs: list[MCPConfig],
    mode: MCPSurfaceMode = MCPSurfaceMode.AUTO,
) -> mcp_routing.MCPRoutingResult:
    return await route_mcp_servers(configs, surface_mode=mode, warmup=warmup)


async def test_a_cold_start_routes_live_and_remembers_the_skill_path_server(
    pool: FakePool, store: ToolTableStore
) -> None:
    _expose(pool, "demo", heavy=True)
    warmup = McpWarmup(store)

    result = await _route(pool, warmup, [config()])
    await warmup.settle()

    assert [skill.name for skill in result.skills] == ["mcp_demo_skill"]
    assert set(pool.asked) == {"demo"}
    stored = store.load("hash-demo")
    assert stored is not None
    assert [tool.name for tool in stored.tools] == ["mcp__demo__a", "mcp__demo__b"]
    assert stored.instructions == "demo instructions."
    assert not warmup.has_jobs


async def test_a_warm_start_builds_the_cold_surface_without_waiting_for_a_session(
    pool: FakePool, store: ToolTableStore
) -> None:
    _expose(pool, "demo", heavy=True)
    cold_warmup = McpWarmup(store)
    cold = await _route(pool, cold_warmup, [config()])
    await cold_warmup.settle()

    warm_pool = FakePool()
    warm_pool.live.update(pool.live)
    with patch(
        "myrm_agent_harness.toolkits.mcp.connection_manager.get_mcp_connection_manager",
        AsyncMock(return_value=warm_pool),
    ):
        warm_warmup = McpWarmup(store)
        warm = await _route(warm_pool, warm_warmup, [config()])

        assert warm.skills == cold.skills
        assert warm.direct_tools == []
        assert warm_pool.asked == []
        assert warm_warmup.has_jobs

        warm_warmup.start()
        await warm_warmup.settle()
        assert warm_pool.asked == ["demo"]


async def test_a_server_within_the_direct_threshold_is_never_served_from_the_cache(
    pool: FakePool, store: ToolTableStore
) -> None:
    _expose(pool, "demo", heavy=False)
    store.save("hash-demo", table_of("mcp__demo__a", "mcp__demo__b"))
    warmup = McpWarmup(store)

    result = await _route(pool, warmup, [config()])
    await warmup.settle()

    assert [tool.name for tool in result.direct_tools] == ["mcp__demo__a", "mcp__demo__b"]
    assert result.skills == []
    assert pool.asked == ["demo"]
    assert not warmup.has_jobs


async def test_forced_direct_mode_never_serves_from_the_cache(pool: FakePool, store: ToolTableStore) -> None:
    _expose(pool, "demo", heavy=True)
    store.save("hash-demo", table_of("mcp__demo__a", "mcp__demo__b"))
    warmup = McpWarmup(store)

    result = await _route(pool, warmup, [config()], MCPSurfaceMode.DIRECT_FC)

    assert len(result.direct_tools) == 2
    assert result.skills == []
    assert pool.asked == ["demo"]
    assert not warmup.has_jobs


async def test_a_pooled_server_takes_the_live_path(pool: FakePool, store: ToolTableStore) -> None:
    _expose(pool, "demo", heavy=True)
    pool.pooled.add("demo")
    store.save("hash-demo", table_of("mcp__demo__a", "mcp__demo__b"))
    warmup = McpWarmup(store)

    result = await _route(pool, warmup, [config()])

    assert [skill.name for skill in result.skills] == ["mcp_demo_skill"]
    assert set(pool.asked) == {"demo"}
    assert not warmup.has_jobs


@pytest.mark.parametrize("cached", ["alpha", "beta"])
async def test_cached_and_live_servers_keep_the_order_of_a_cold_start(
    pool: FakePool, store: ToolTableStore, cached: str
) -> None:
    _expose(pool, "alpha", heavy=True)
    _expose(pool, "beta", heavy=True)
    _expose(pool, "gamma", heavy=False)
    configs = [config("alpha"), config("beta"), config("gamma")]
    cold_warmup = McpWarmup(store)
    cold = await _route(pool, cold_warmup, configs)
    await cold_warmup.settle()
    assert [skill.name for skill in cold.skills] == ["mcp_alpha_skill", "mcp_beta_skill"]
    other = "beta" if cached == "alpha" else "alpha"
    store.discard(f"hash-{other}")

    warm_pool = FakePool()
    warm_pool.live.update(pool.live)
    with patch(
        "myrm_agent_harness.toolkits.mcp.connection_manager.get_mcp_connection_manager",
        AsyncMock(return_value=warm_pool),
    ):
        warm = await _route(warm_pool, McpWarmup(store), configs)

    assert warm.skills == cold.skills
    assert [tool.name for tool in warm.direct_tools] == [tool.name for tool in cold.direct_tools]
    assert set(warm_pool.asked) == {"gamma", other}


async def test_a_server_that_fails_to_connect_is_skipped_beside_a_served_one(
    pool: FakePool, store: ToolTableStore
) -> None:
    store.save("hash-alpha", table_of("mcp__alpha__a", "mcp__alpha__b", schema_chars=_HEAVY))
    warmup = McpWarmup(store)

    result = await _route(pool, warmup, [config("alpha"), config("broken")])

    assert [skill.name for skill in result.skills] == ["mcp_alpha_skill"]
    assert pool.asked == ["broken"]
