"""create_skill_agent adds the warm-up middleware exactly when a server was served from its cached tool table.

[INPUT]
- myrm_agent_harness.agent._factory.builder::create_skill_agent (POS: unit under test)
- myrm_agent_harness.agent.middlewares.mcp_warmup_middleware::McpWarmupMiddleware (POS: the middleware that starts the sessions)
- tests.support.mcp_warmup_doubles (POS: the pool double and the tool builders)

[OUTPUT]
- Tests of the middleware list handed to the agent for a cold start, a warm start, host middlewares and no MCP servers.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.agents.middleware import AgentMiddleware, AgentState

from myrm_agent_harness.agent._factory import mcp_routing
from myrm_agent_harness.agent._factory.builder import create_skill_agent
from myrm_agent_harness.agent.middlewares.mcp_warmup_middleware import McpWarmupMiddleware
from myrm_agent_harness.agent.types import AgentRuntimeSpec
from myrm_agent_harness.toolkits.mcp.config import MCPConfig
from myrm_agent_harness.toolkits.mcp.tool_table_store import ToolTableStore
from tests.support.mcp_warmup_doubles import FakeConnection, FakePool, config, live_tools, table_of


@pytest.fixture
def pool(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[FakePool]:
    fake = FakePool()
    fake.live["demo"] = FakeConnection("demo", live_tools("mcp__demo__a", "mcp__demo__b"))
    monkeypatch.setattr(mcp_routing, "compute_direct_threshold", lambda *_: 0)
    monkeypatch.setattr(ToolTableStore, "at_state_root", classmethod(lambda cls: ToolTableStore(tmp_path / "tables")))
    with (
        patch(
            "myrm_agent_harness.toolkits.mcp.connection_manager.get_mcp_connection_manager",
            AsyncMock(return_value=fake),
        ),
        patch("myrm_agent_harness.agent.skills.runtime.registry.skill_registry.register"),
    ):
        yield fake


type _Middleware = AgentMiddleware[AgentState[object], None, object]


class _HostMiddleware(AgentMiddleware[AgentState[object], None, object]):
    """A middleware the host adds; it does nothing."""


async def _middlewares_given_to_the_agent(
    spec: AgentRuntimeSpec, host_middlewares: list[_Middleware] | None = None
) -> list[object]:
    with patch("myrm_agent_harness.agent.skill_agent.SkillAgent") as agent_class:
        await create_skill_agent(
            spec=spec, llm=MagicMock(), executor=MagicMock(), middlewares=host_middlewares, fallback_llm=MagicMock()
        )
    return list(agent_class.call_args.kwargs["middlewares"])


def _spec(servers: list[MCPConfig]) -> AgentRuntimeSpec:
    return AgentRuntimeSpec(agent_id="agent", name="agent", system_prompt="test", mcp_servers=servers)


def _warmups(middlewares: list[object]) -> list[McpWarmupMiddleware]:
    return [item for item in middlewares if isinstance(item, McpWarmupMiddleware)]


async def test_a_cold_start_adds_no_warm_up_middleware(pool: FakePool) -> None:
    middlewares = await _middlewares_given_to_the_agent(_spec([config()]))

    assert _warmups(middlewares) == []
    assert pool.asked


async def test_a_warm_start_adds_the_warm_up_middleware_and_connects_nothing_yet(
    pool: FakePool, tmp_path: Path
) -> None:
    ToolTableStore(tmp_path / "tables").save("hash-demo", table_of("mcp__demo__a", "mcp__demo__b", schema_chars=50))

    middlewares = await _middlewares_given_to_the_agent(_spec([config()]))

    assert len(_warmups(middlewares)) == 1
    assert pool.asked == []


async def test_host_middlewares_are_kept_and_the_caller_list_is_not_mutated(pool: FakePool, tmp_path: Path) -> None:
    ToolTableStore(tmp_path / "tables").save("hash-demo", table_of("mcp__demo__a", "mcp__demo__b", schema_chars=50))
    host = _HostMiddleware()
    host_list: list[_Middleware] = [host]

    middlewares = await _middlewares_given_to_the_agent(_spec([config()]), host_list)

    assert middlewares[0] is host
    assert len(_warmups(middlewares)) == 1
    assert host_list == [host]


async def test_no_mcp_servers_means_no_warm_up(pool: FakePool) -> None:
    middlewares = await _middlewares_given_to_the_agent(_spec([]))

    assert _warmups(middlewares) == []
    assert pool.asked == []
