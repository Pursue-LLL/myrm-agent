"""MCP Skill generation from a surface the caller already holds (a restored tool table) instead of a live session.

[INPUT]
- myrm_agent_harness.agent.skills.mcp.core_generator (POS: unit under test)
- myrm_agent_harness.toolkits.mcp.tool_table (POS: captures and restores the surface)

[OUTPUT]
- Tests that a restored surface yields the same L1/L2/L3 text and token estimate as the live tools, and that servers
  with a known surface are generated without a connection while the others still connect.
"""

from __future__ import annotations

import pytest
from langchain_core.tools import BaseTool
from mcp.types import Tool

from myrm_agent_harness.agent.skills.mcp.core_generator import mcp_skill_generator
from myrm_agent_harness.backends.skills.types import SkillMetadata
from myrm_agent_harness.toolkits.mcp.config import MCPConfig, mcp_config_to_runtime_dict
from myrm_agent_harness.toolkits.mcp.tool_converter import convert_mcp_tools
from myrm_agent_harness.toolkits.mcp.tool_table import ServerSurface, capture_table, restore_surface
from myrm_agent_harness.utils.token_estimation import estimate_tools_schema_tokens


async def _unused_call(name: str, arguments: dict[str, object]) -> object:
    raise AssertionError("a surface test never calls a tool")


def _live_tools(prefix: str = "demo", count: int = 6) -> list[BaseTool]:
    """Tools as a live session exposes them; every other tool also declares an output schema."""
    definitions = [
        Tool(
            name=f"mcp__{prefix}__tool_{index}",
            description=f"Tool {index} of {prefix}. It does one thing well, and it says so in several words.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to look for"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    "mode": {"enum": ["fast", "full"]},
                },
                "required": ["query"],
            },
            output_schema=(
                {"type": "object", "properties": {"hits": {"type": "array", "items": {"type": "string"}}}}
                if index % 2
                else None
            ),
        )
        for index in range(count)
    ]
    return list(convert_mcp_tools(definitions, _unused_call, server_name=prefix))


def _restored(tools: list[BaseTool], instructions: str | None = None) -> ServerSurface:
    table = capture_table(ServerSurface(tools=tuple(tools), instructions=instructions))
    assert table is not None
    return restore_surface(table)


def _config(name: str) -> MCPConfig:
    return MCPConfig(name=name, type="stdio", command="echo")


@pytest.mark.parametrize("instructions", [None, "Search before you list. Never page past ten results."])
def test_a_restored_surface_yields_the_text_the_live_tools_yield(instructions: str | None) -> None:
    live = _live_tools()
    restored = _restored(live, instructions)

    from_live = mcp_skill_generator._create_skill_metadata("demo", live, "", instructions)
    from_table = mcp_skill_generator._create_skill_metadata("demo", list(restored.tools), "", instructions)

    assert from_table == from_live
    assert mcp_skill_generator.generate_skill_content(from_table) == mcp_skill_generator.generate_skill_content(
        from_live
    )
    for tool in live:
        assert mcp_skill_generator.generate_tool_doc(from_table, tool.name) == mcp_skill_generator.generate_tool_doc(
            from_live, tool.name
        )


def test_a_restored_surface_weighs_what_the_live_tools_weigh() -> None:
    live = _live_tools(count=40)

    assert estimate_tools_schema_tokens(_restored(live).tools) == estimate_tools_schema_tokens(live)


class _Connection:
    def __init__(self, server: str, tools: list[BaseTool], instructions: str | None = None) -> None:
        self.tools_by_server = {server: tools}
        self.instructions_by_server = {server: instructions}


class _Pool:
    """Hands out the connection of each configured server and records who was asked."""

    def __init__(self, *connections: _Connection) -> None:
        self._by_server = {next(iter(conn.tools_by_server)): conn for conn in connections}
        self.asked: list[str] = []

    async def get_connection(self, configs: list[MCPConfig]) -> _Connection:
        self.asked.append(configs[0].name)
        if configs[0].name not in self._by_server:
            raise ConnectionError("down")
        return self._by_server[configs[0].name]


def _use_pool(monkeypatch: pytest.MonkeyPatch, pool: _Pool) -> None:
    async def _manager() -> _Pool:
        return pool

    monkeypatch.setattr("myrm_agent_harness.toolkits.mcp.connection_manager.get_mcp_connection_manager", _manager)


async def test_a_known_surface_is_generated_without_asking_the_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = _Pool()
    _use_pool(monkeypatch, pool)
    live = _live_tools()

    skills = await mcp_skill_generator.generate_metadata_only(
        [_config("demo")], {"demo": _restored(live, "Search first.")}
    )

    expected: SkillMetadata = mcp_skill_generator._create_skill_metadata("demo", live, "", "Search first.")
    assert expected.mcp is not None
    expected.mcp.config = [mcp_config_to_runtime_dict(_config("demo"))]
    assert pool.asked == []
    assert skills == [expected]


async def test_known_and_live_servers_mix_in_configured_order(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = _Pool(_Connection("live", _live_tools("live", count=3)))
    _use_pool(monkeypatch, pool)
    known = {"cached": _restored(_live_tools("cached", count=3))}

    skills = await mcp_skill_generator.generate_metadata_only([_config("cached"), _config("live")], known)

    assert [skill.name for skill in skills] == ["mcp_cached_skill", "mcp_live_skill"]
    assert pool.asked == ["live"]


async def test_names_that_collide_stay_distinct_across_known_and_live_servers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = _Pool(_Connection("weather-skill", _live_tools("weather_skill", count=2)))
    _use_pool(monkeypatch, pool)
    known = {"weather": _restored(_live_tools("weather", count=2))}

    skills = await mcp_skill_generator.generate_metadata_only([_config("weather"), _config("weather-skill")], known)

    assert [skill.name for skill in skills] == ["mcp_weather_skill", "mcp_weather_skill_2"]


async def test_a_known_surface_without_tools_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_pool(monkeypatch, _Pool())
    empty = ServerSurface(tools=(), instructions=None)

    assert await mcp_skill_generator.generate_metadata_only([_config("demo")], {"demo": empty}) == []


async def test_a_live_server_that_fails_to_connect_does_not_disturb_the_known_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = _Pool()
    _use_pool(monkeypatch, pool)
    known = {"cached": _restored(_live_tools("cached", count=2))}

    skills = await mcp_skill_generator.generate_metadata_only([_config("broken"), _config("cached")], known)

    assert [skill.name for skill in skills] == ["mcp_cached_skill"]
    assert pool.asked == ["broken"]
