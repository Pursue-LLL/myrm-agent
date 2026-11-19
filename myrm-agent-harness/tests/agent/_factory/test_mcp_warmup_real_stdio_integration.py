"""Integration proof: a real stdio MCP server is routed from its cached tool table, then verified by its live session.

[INPUT]
- myrm_agent_harness.agent._factory.mcp_routing::route_mcp_servers (POS: routes from the cached table when given a warm-up)
- myrm_agent_harness.toolkits.mcp.warmup::McpWarmup (POS: serves the table and starts the session later)
- tests.support.mcp_testkit.cancel_probe_server (POS: the real stdio server the connection talks to)

[OUTPUT]
- Integration tests of a cold start that fills the cache, a warm start that starts no server until asked, the safety
  metadata that appears only with the live session, and a cached server that has gone away.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from myrm_agent_harness.agent._factory import mcp_routing
from myrm_agent_harness.agent._factory.mcp_routing import route_mcp_servers
from myrm_agent_harness.agent.skills.runtime.registry import skill_registry
from myrm_agent_harness.core.security.tool_registry.registry import (
    evict_skill_safety_metadata,
    get_ptc_safety_metadata,
)
from myrm_agent_harness.toolkits.mcp.config import MCPConfig
from myrm_agent_harness.toolkits.mcp.connection_manager import MCPConnectionManager
from myrm_agent_harness.toolkits.mcp.tool_table_store import ToolTableStore
from myrm_agent_harness.toolkits.mcp.warmup import McpWarmup
from tests.support.mcp_testkit import cancel_probe_server

_SKILL = "mcp_probe_skill"
_FAST_TOOL = "mcp__probe__fast"


@pytest.fixture
def fresh_process(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every server goes to the Skill path (as in a forced-PTC run), and the pool and registries start empty."""
    monkeypatch.setattr(mcp_routing, "compute_direct_threshold", lambda *_: 0)
    MCPConnectionManager._instance = None
    skill_registry.clear()
    evict_skill_safety_metadata(_SKILL)
    yield
    MCPConnectionManager._instance = None
    skill_registry.clear()
    evict_skill_safety_metadata(_SKILL)


def _probe_config(tmp_path: Path) -> MCPConfig:
    return MCPConfig(
        name="probe",
        type="stdio",
        command=sys.executable,
        args=[cancel_probe_server.__file__, str(tmp_path)],
        connect_timeout=45.0,
    )


async def _restart_process() -> MCPConnectionManager:
    """What a new process starts with: an empty pool and no tool safety metadata."""
    manager = await MCPConnectionManager.get_instance()
    await manager.stop()
    MCPConnectionManager._instance = None
    skill_registry.clear()
    evict_skill_safety_metadata(_SKILL)
    return await MCPConnectionManager.get_instance()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_a_warm_start_builds_the_cold_surface_and_starts_no_server_until_asked(
    tmp_path: Path, fresh_process: None
) -> None:
    cfg = _probe_config(tmp_path)
    store = ToolTableStore(tmp_path / "tables")

    cold_warmup = McpWarmup(store)
    cold = await route_mcp_servers([cfg], warmup=cold_warmup)
    await cold_warmup.settle()
    assert [skill.name for skill in cold.skills] == [_SKILL]
    assert get_ptc_safety_metadata(_SKILL, _FAST_TOOL) is not None

    manager = await _restart_process()
    try:
        warm_warmup = McpWarmup(store)
        warm = await route_mcp_servers([cfg], warmup=warm_warmup)

        assert warm.skills == cold.skills
        assert not manager.is_pooled([cfg])
        assert get_ptc_safety_metadata(_SKILL, _FAST_TOOL) is None

        warm_warmup.start()
        await warm_warmup.settle()

        assert manager.is_pooled([cfg])
        assert get_ptc_safety_metadata(_SKILL, _FAST_TOOL) is not None
    finally:
        await manager.stop()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_a_cached_server_that_has_gone_away_loses_its_entry(tmp_path: Path, fresh_process: None) -> None:
    cfg = _probe_config(tmp_path)
    store = ToolTableStore(tmp_path / "tables")
    cold_warmup = McpWarmup(store)
    await route_mcp_servers([cfg], warmup=cold_warmup)
    await cold_warmup.settle()
    manager = await _restart_process()
    try:
        gone = MCPConfig(name="probe", type="stdio", command=str(tmp_path / "no-such-server"), connect_timeout=10.0)
        key = manager.config_hash([gone])
        stored = store.load(manager.config_hash([cfg]))
        assert stored is not None
        store.save(key, stored)

        warmup = McpWarmup(store)
        served = await route_mcp_servers([gone], warmup=warmup)
        assert [skill.name for skill in served.skills] == [_SKILL]

        warmup.start()
        await warmup.settle()

        assert store.load(key) is None
        assert not manager.is_pooled([gone])
    finally:
        await manager.stop()
