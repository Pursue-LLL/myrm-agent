"""Unit tests for SandboxCapableAgentAutoExtractL3WriteGate."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai_agents import GeneralAgentParams
from app.services.agent.params.converter import convert_to_general_agent_params
from app.services.agent.params.models import AgentRequest
from app.services.agent.profile.profile_builtin_tools import is_sandbox_capable_tools
from app.services.agent.profile.profile_resolver import ResolvedAgentProfile
from tests.api.agent.conftest import _build_mock_user_configs
from tests.api.agent.utils import get_model_selection


class TestIsSandboxCapableTools:
    def test_code_execute_detected(self) -> None:
        tools = ["web_search", "code_execute", "memory"]
        assert is_sandbox_capable_tools(tools) is True

    def test_external_cli_detected(self) -> None:
        tools = ["web_search", "external_cli"]
        assert is_sandbox_capable_tools(tools) is True

    def test_declared_capabilities_detected(self) -> None:
        tools = ["web_search", "memory"]
        assert is_sandbox_capable_tools(tools, declared_capabilities=("code_execution",)) is True
        assert is_sandbox_capable_tools(tools, declared_capabilities=("sandbox",)) is True
        assert is_sandbox_capable_tools(tools, declared_capabilities=("terminal",)) is True
        assert is_sandbox_capable_tools(tools, declared_capabilities=("coding",)) is True

    def test_general_agent_tools_not_sandbox(self) -> None:
        tools = ["web_search", "memory", "structured_clarify", "wiki", "kanban"]
        assert is_sandbox_capable_tools(tools) is False


class TestResolvedAgentProfileProperty:
    def test_profile_is_sandbox_capable(self) -> None:
        coding_profile = ResolvedAgentProfile(
            agent_id="coding-agent-1",
            skill_ids=(),
            mcp_ids=(),
            enabled_builtin_tools=("code_execute", "file_ops", "web_search"),
        )
        assert coding_profile.is_sandbox_capable is True

        general_profile = ResolvedAgentProfile(
            agent_id="general-agent-1",
            skill_ids=(),
            mcp_ids=(),
            enabled_builtin_tools=("web_search", "memory"),
        )
        assert general_profile.is_sandbox_capable is False


async def convert(*, builtin_tools: tuple[str, ...], **request_fields: bool) -> GeneralAgentParams:
    """Run the real converter for an agent with ``builtin_tools``; memory and auto-extraction start switched on."""
    profile = ResolvedAgentProfile(agent_id="agent-1", skill_ids=(), mcp_ids=(), enabled_builtin_tools=builtin_tools)
    resolver = MagicMock()
    resolver.resolve = AsyncMock(return_value=profile)
    request = AgentRequest(
        message_id="msg-1",
        query="Remember that my deploy host is 10.0.0.5:8080",
        chat_id="chat-1",
        agent_id="agent-1",
        model_selection=get_model_selection(),
        **{"enable_memory": True, "enable_memory_auto_extraction": True, **request_fields},
    )
    with (
        patch("app.services.agent.profile.profile_resolver.get_agent_profile_resolver", return_value=resolver),
        patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=_build_mock_user_configs())),
    ):
        params, *_ = await convert_to_general_agent_params(request, chat_history=[])
    return params


class TestConverterSandboxWriteGate:
    @pytest.mark.asyncio
    async def test_sandbox_profile_disables_auto_extraction_by_default(self) -> None:
        params = await convert(builtin_tools=("code_execute", "web_search"), memory_require_confirmation=False)

        assert params.enable_memory_auto_extraction is False
        assert params.memory_require_confirmation is True

    @pytest.mark.asyncio
    async def test_general_profile_retains_auto_extraction(self) -> None:
        params = await convert(builtin_tools=("web_search", "memory"), memory_require_confirmation=False)

        assert params.enable_memory_auto_extraction is True
        assert params.memory_require_confirmation is False

    @pytest.mark.asyncio
    async def test_incognito_mode_overrides_all(self) -> None:
        params = await convert(builtin_tools=("web_search", "memory"), incognito_mode=True)

        assert params.enable_memory_auto_extraction is False

    @pytest.mark.asyncio
    async def test_incognito_mode_keeps_memory_on(self) -> None:
        params = await convert(builtin_tools=("web_search", "memory"), incognito_mode=True)

        assert params.enable_memory is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("builtin_tools", "request_fields"),
        [
            pytest.param(("web_search",), {"enable_memory": False}, id="memory-off"),
            pytest.param(("web_search",), {"enable_memory_auto_extraction": False}, id="extraction-off"),
            pytest.param(("web_search", "external_cli"), {}, id="external-cli-agent"),
        ],
    )
    async def test_auto_extraction_stays_off_when_any_of_its_conditions_fails(
        self, builtin_tools: tuple[str, ...], request_fields: dict[str, bool]
    ) -> None:
        params = await convert(builtin_tools=builtin_tools, **request_fields)

        assert params.enable_memory_auto_extraction is False
