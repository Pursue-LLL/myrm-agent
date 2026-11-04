"""How the MCP proxy hands a failed call to a Python script: as an exception, and never as a cacheable result."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.agent.skills.mcp.cache_policy import get_cache_buckets
from myrm_agent_harness.agent.skills.mcp.proxy_service import MCPSkillProxyService
from myrm_agent_harness.agent.skills.runtime.registry import skill_registry
from myrm_agent_harness.backends.skills.types import MCPSkillData, SkillMetadata
from myrm_agent_harness.toolkits.mcp.config import MCPConfig
from myrm_agent_harness.toolkits.mcp.errors import MCPToolFailure

_MANAGER = "myrm_agent_harness.toolkits.mcp.connection_manager.get_mcp_connection_manager"
_MARGIN = "myrm_agent_harness.agent.skills.mcp.call_backstop.BACKSTOP_MARGIN_SECONDS"
_TIMEOUT_TEXT = "MCP tool 'mcp__srv__ping' timed out after 2.0s. Server may be slow or unresponsive."


@pytest.fixture(autouse=True)
def _clean_state() -> Iterator[None]:
    skill_registry.clear()
    get_cache_buckets().clear()
    yield
    skill_registry.clear()
    get_cache_buckets().clear()


def _cacheable_skill() -> SkillMetadata:
    return SkillMetadata(
        name="mcp_test_skill",
        description="Test MCP skill",
        mcp=MCPSkillData(
            server="srv",
            tools=["ping"],
            config=[
                {
                    "name": "srv",
                    "type": "stdio",
                    "command": "echo",
                    "cache_ttl_seconds": 60,
                    "cacheable_tools": ["ping"],
                }
            ],
            tool_schemas={"ping": {"inputSchema": {"type": "object", "properties": {}}}},
        ),
    )


def _manager_for(call: AsyncMock) -> MagicMock:
    conn = MagicMock()
    conn.call = call
    manager = MagicMock()
    manager.get_connection = AsyncMock(return_value=conn)
    return manager


def _server(name: str, execute_timeout: float) -> MCPConfig:
    return MCPConfig(name=name, type="stdio", command="echo", description="d", execute_timeout=execute_timeout)


class TestMarkedFailures:
    @pytest.mark.asyncio
    async def test_a_marked_failure_is_raised_to_the_script(self) -> None:
        skill_registry.register(_cacheable_skill())
        manager = _manager_for(AsyncMock(return_value=MCPToolFailure(_TIMEOUT_TEXT)))

        with (
            patch(_MANAGER, AsyncMock(return_value=manager)),
            pytest.raises(RuntimeError, match=r"timed out after 2\.0s"),
        ):
            await MCPSkillProxyService().invoke_tool("mcp_test_skill", "ping", {}, session_id="s1")

    @pytest.mark.asyncio
    async def test_a_failure_is_not_remembered_as_the_result_of_the_call(self) -> None:
        skill_registry.register(_cacheable_skill())
        service = MCPSkillProxyService()
        call = AsyncMock(side_effect=[MCPToolFailure(_TIMEOUT_TEXT), ({"type": "text", "text": "pong"}, None)])
        manager = _manager_for(call)

        with patch(_MANAGER, AsyncMock(return_value=manager)):
            with pytest.raises(RuntimeError):
                await service.invoke_tool("mcp_test_skill", "ping", {}, session_id="s1")
            second = await service.invoke_tool("mcp_test_skill", "ping", {}, session_id="s1")

        assert second == "pong"
        assert call.await_count == 2

    @pytest.mark.asyncio
    async def test_a_server_reply_that_reads_like_a_failure_is_still_data(self) -> None:
        skill_registry.register(_cacheable_skill())
        manager = _manager_for(AsyncMock(return_value=_TIMEOUT_TEXT))

        with patch(_MANAGER, AsyncMock(return_value=manager)):
            result = await MCPSkillProxyService().invoke_tool("mcp_test_skill", "ping", {}, session_id="s1")

        assert result == _TIMEOUT_TEXT


class TestCallBackstop:
    @pytest.mark.asyncio
    async def test_a_call_that_outlives_its_configured_limit_raises_a_named_timeout(self) -> None:
        async def never_answers(*_: object) -> None:
            await asyncio.sleep(30)

        manager = _manager_for(AsyncMock(side_effect=never_answers))

        with (
            patch(_MANAGER, AsyncMock(return_value=manager)),
            patch(_MARGIN, 0.2),
            pytest.raises(TimeoutError, match=r"'srv\.ping' timed out after 1\.2s"),
        ):
            await MCPSkillProxyService()._find_and_invoke([_server("srv", 1.0)], "srv", "ping", {})

    @pytest.mark.asyncio
    async def test_the_connection_phase_is_not_charged_to_the_call(self) -> None:
        async def slow_connect(*_: object) -> MagicMock:
            await asyncio.sleep(1.5)
            return conn

        conn = MagicMock()
        conn.call = AsyncMock(return_value=({"type": "text", "text": "done"}, None))
        manager = MagicMock()
        manager.get_connection = slow_connect

        with patch(_MANAGER, AsyncMock(return_value=manager)), patch(_MARGIN, 0.2):
            result = await MCPSkillProxyService()._find_and_invoke([_server("srv", 1.0)], "srv", "ping", {})

        assert result == "done"

    @pytest.mark.asyncio
    async def test_the_limit_is_the_largest_one_configured_for_the_skill(self) -> None:
        async def takes_a_while(*_: object) -> tuple[dict[str, str], None]:
            await asyncio.sleep(1.6)
            return {"type": "text", "text": "late but within the larger limit"}, None

        manager = _manager_for(AsyncMock(side_effect=takes_a_while))

        with patch(_MANAGER, AsyncMock(return_value=manager)), patch(_MARGIN, 0.2):
            result = await MCPSkillProxyService()._find_and_invoke(
                [_server("small", 1.0), _server("large", 3.0)], "large", "ping", {}
            )

        assert result == "late but within the larger limit"
