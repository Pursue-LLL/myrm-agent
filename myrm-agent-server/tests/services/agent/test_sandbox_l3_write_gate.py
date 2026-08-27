"""Unit tests for SandboxCapableAgentAutoExtractL3WriteGate."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.agent.profile.profile_builtin_tools import is_sandbox_capable_tools
from app.services.agent.profile.profile_resolver import ResolvedAgentProfile
from app.services.agent.params.converter import convert_to_general_agent_params
from app.services.agent.params.models import AgentRequest
from tests.api.agent.conftest import _build_mock_user_configs
from tests.api.agent.utils import get_model_selection


class TestIsSandboxCapableTools:
    def test_code_execute_detected(self) -> None:
        tools = ["web_search", "code_execute", "memory"]
        assert is_sandbox_capable_tools(tools) is True

    def test_external_cli_detected(self) -> None:
        tools = ["web_search", "external_cli"]
        assert is_sandbox_capable_tools(tools) is True

    def test_sandbox_dir_detected(self) -> None:
        tools = ["web_search", "memory"]
        assert is_sandbox_capable_tools(tools, has_sandbox_dir=True) is True

    def test_declared_capabilities_detected(self) -> None:
        tools = ["web_search", "memory"]
        assert is_sandbox_capable_tools(tools, declared_capabilities=("code_execution",)) is True
        assert is_sandbox_capable_tools(tools, declared_capabilities=("sandbox",)) is True
        assert is_sandbox_capable_tools(tools, declared_capabilities=("terminal",)) is True
        assert is_sandbox_capable_tools(tools, declared_capabilities=("coding",)) is True

    def test_general_agent_tools_not_sandbox(self) -> None:
        tools = ["web_search", "memory", "render_ui", "structured_clarify", "wiki", "kanban"]
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
            enabled_builtin_tools=("web_search", "memory", "render_ui"),
        )
        assert general_profile.is_sandbox_capable is False


class TestConverterSandboxWriteGate:
    @pytest.mark.asyncio
    async def test_sandbox_profile_disables_auto_extraction_by_default(self) -> None:
        coding_profile = ResolvedAgentProfile(
            agent_id="coding-agent-1",
            skill_ids=(),
            mcp_ids=(),
            enabled_builtin_tools=("code_execute", "web_search"),
        )
        mock_resolver = MagicMock()
        mock_resolver.resolve = AsyncMock(return_value=coding_profile)

        req = AgentRequest(
            message_id="msg-1",
            query="Refactor auth",
            chat_id="chat-coding",
            agent_id="coding-agent-1",
            enable_memory=True,
            enable_memory_auto_extraction=True,
            memory_require_confirmation=False,
            model_selection=get_model_selection(),
        )

        mock_configs = _build_mock_user_configs()
        with patch("app.services.agent.profile.profile_resolver.get_agent_profile_resolver", return_value=mock_resolver), \
             patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=mock_configs)):
            params, _, _, _, _ = await convert_to_general_agent_params(req, chat_history=[])

        assert params.enable_memory_auto_extraction is False
        assert params.memory_require_confirmation is True

    @pytest.mark.asyncio
    async def test_general_profile_retains_auto_extraction(self) -> None:
        general_profile = ResolvedAgentProfile(
            agent_id="general-agent-1",
            skill_ids=(),
            mcp_ids=(),
            enabled_builtin_tools=("web_search", "memory", "render_ui"),
        )
        mock_resolver = MagicMock()
        mock_resolver.resolve = AsyncMock(return_value=general_profile)

        req = AgentRequest(
            message_id="msg-2",
            query="Tell me a joke",
            chat_id="chat-general",
            agent_id="general-agent-1",
            enable_memory=True,
            enable_memory_auto_extraction=True,
            memory_require_confirmation=False,
            model_selection=get_model_selection(),
        )

        mock_configs = _build_mock_user_configs()
        with patch("app.services.agent.profile.profile_resolver.get_agent_profile_resolver", return_value=mock_resolver), \
             patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=mock_configs)):
            params, _, _, _, _ = await convert_to_general_agent_params(req, chat_history=[])

        assert params.enable_memory_auto_extraction is True
        assert params.memory_require_confirmation is False

    @pytest.mark.asyncio
    async def test_incognito_mode_overrides_all(self) -> None:
        general_profile = ResolvedAgentProfile(
            agent_id="general-agent-1",
            skill_ids=(),
            mcp_ids=(),
            enabled_builtin_tools=("web_search", "memory", "render_ui"),
        )
        mock_resolver = MagicMock()
        mock_resolver.resolve = AsyncMock(return_value=general_profile)

        req = AgentRequest(
            message_id="msg-3",
            query="Secret query",
            chat_id="chat-incognito",
            agent_id="general-agent-1",
            enable_memory=True,
            enable_memory_auto_extraction=True,
            incognito_mode=True,
            model_selection=get_model_selection(),
        )

        mock_configs = _build_mock_user_configs()
        with patch("app.services.agent.profile.profile_resolver.get_agent_profile_resolver", return_value=mock_resolver), \
             patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=mock_configs)):
            params, _, _, _, _ = await convert_to_general_agent_params(req, chat_history=[])

        assert params.enable_memory_auto_extraction is False
