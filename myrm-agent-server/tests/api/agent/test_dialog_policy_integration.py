"""Integration test: dialog_policy and session_recording parameter propagation.

Verifies that dialog_policy and session_recording set in AgentConfigRequest flow
correctly through convert_to_general_agent_params → GeneralAgentParams without
being lost or mutated.

This is a focused integration test covering the full converter logic (no LLM mock),
only mocking external IO (DB, config loader).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.params.models import AgentConfigRequest, AgentRequest
from tests.api.agent.utils import get_model_selection


@pytest.fixture
def base_request() -> dict:
    """Minimal valid AgentRequest fields."""
    return {
        "message_id": "test-msg-dialog-policy",
        "chat_id": "test-chat-dialog",
        "query": "hello",
        "model_selection": get_model_selection(),
    }


class TestDialogPolicyConverterIntegration:
    """Converter correctly propagates dialog_policy from request to GeneralAgentParams."""

    @pytest.mark.asyncio
    async def test_dialog_policy_from_agent_config(self, base_request: dict):
        """dialog_policy in agent_config reaches GeneralAgentParams."""
        from app.services.agent.params.converter import convert_to_general_agent_params

        base_request["agent_config"] = {
            "dialogPolicy": "wait_for_agent",
            "enabledBuiltinTools": ["web_search"],
        }
        request = AgentRequest(**base_request)

        params, _, _, _ = await convert_to_general_agent_params(request, [])
        assert params.dialog_policy == "wait_for_agent"

    @pytest.mark.asyncio
    async def test_dialog_policy_none_by_default(self, base_request: dict):
        """Without agent_config, dialog_policy defaults to None."""
        from app.services.agent.params.converter import convert_to_general_agent_params

        request = AgentRequest(**base_request)

        params, _, _, _ = await convert_to_general_agent_params(request, [])
        assert params.dialog_policy is None

    @pytest.mark.asyncio
    async def test_dialog_policy_auto_accept(self, base_request: dict):
        """auto_accept policy propagates correctly."""
        from app.services.agent.params.converter import convert_to_general_agent_params

        base_request["agent_config"] = {
            "dialogPolicy": "auto_accept",
            "enabledBuiltinTools": ["web_search"],
        }
        request = AgentRequest(**base_request)

        params, _, _, _ = await convert_to_general_agent_params(request, [])
        assert params.dialog_policy == "auto_accept"

    @pytest.mark.asyncio
    async def test_dialog_policy_auto_dismiss(self, base_request: dict):
        """auto_dismiss policy propagates correctly."""
        from app.services.agent.params.converter import convert_to_general_agent_params

        base_request["agent_config"] = {
            "dialogPolicy": "auto_dismiss",
            "enabledBuiltinTools": ["web_search"],
        }
        request = AgentRequest(**base_request)

        params, _, _, _ = await convert_to_general_agent_params(request, [])
        assert params.dialog_policy == "auto_dismiss"

    @pytest.mark.asyncio
    async def test_dialog_policy_smart(self, base_request: dict):
        """Explicit 'smart' policy propagates correctly."""
        from app.services.agent.params.converter import convert_to_general_agent_params

        base_request["agent_config"] = {
            "dialogPolicy": "smart",
            "enabledBuiltinTools": ["web_search"],
        }
        request = AgentRequest(**base_request)

        params, _, _, _ = await convert_to_general_agent_params(request, [])
        assert params.dialog_policy == "smart"

    @pytest.mark.asyncio
    async def test_dialog_policy_from_resolved_profile(self, base_request: dict):
        """dialog_policy stored in agent profile flows through resolver."""
        from app.services.agent.params.converter import convert_to_general_agent_params
        from app.services.agent.profile_resolver import ResolvedAgentProfile

        base_request["agent_id"] = "test-agent-with-dialog-policy"
        request = AgentRequest(**base_request)

        mock_profile = ResolvedAgentProfile(
            agent_id="test-agent-with-dialog-policy",
            skill_ids=(),
            mcp_ids=(),
            enabled_builtin_tools=("web_search",),
            system_prompt="",
            auto_restore_domains=(),
            engine_params={},
            dialog_policy="wait_for_agent",
        )

        mock_resolver = AsyncMock()
        mock_resolver.resolve = AsyncMock(return_value=mock_profile)

        with patch(
            "app.services.agent.profile_resolver.get_agent_profile_resolver",
            return_value=mock_resolver,
        ):
            params, _, _, _ = await convert_to_general_agent_params(request, [])
            assert params.dialog_policy == "wait_for_agent"


class TestDialogPolicyRequestParsing:
    """AgentConfigRequest correctly parses dialog_policy from camelCase JSON."""

    def test_camel_case_parsing(self):
        cfg = AgentConfigRequest(**{"dialogPolicy": "auto_dismiss"})
        assert cfg.dialog_policy == "auto_dismiss"

    def test_snake_case_parsing(self):
        cfg = AgentConfigRequest(dialog_policy="wait_for_agent")
        assert cfg.dialog_policy == "wait_for_agent"

    def test_none_default(self):
        cfg = AgentConfigRequest()
        assert cfg.dialog_policy is None

    def test_validation_rejects_invalid(self):
        with pytest.raises(ValueError, match="dialog_policy must be one of"):
            AgentConfigRequest(dialog_policy="invalid_value")


class TestSessionRecordingConverterIntegration:
    """Converter correctly propagates session_recording from request to GeneralAgentParams."""

    @pytest.mark.asyncio
    async def test_session_recording_from_agent_config(self, base_request: dict):
        """session_recording in agent_config reaches GeneralAgentParams."""
        from app.services.agent.params.converter import convert_to_general_agent_params

        base_request["agent_config"] = {
            "sessionRecording": "always",
            "enabledBuiltinTools": ["web_search"],
        }
        request = AgentRequest(**base_request)

        params, _, _, _ = await convert_to_general_agent_params(request, [])
        assert params.session_recording == "always"

    @pytest.mark.asyncio
    async def test_session_recording_on_failure(self, base_request: dict):
        """on_failure mode propagates correctly."""
        from app.services.agent.params.converter import convert_to_general_agent_params

        base_request["agent_config"] = {
            "sessionRecording": "on_failure",
            "enabledBuiltinTools": ["web_search"],
        }
        request = AgentRequest(**base_request)

        params, _, _, _ = await convert_to_general_agent_params(request, [])
        assert params.session_recording == "on_failure"

    @pytest.mark.asyncio
    async def test_session_recording_none_by_default(self, base_request: dict):
        """Without agent_config, session_recording defaults to None."""
        from app.services.agent.params.converter import convert_to_general_agent_params

        request = AgentRequest(**base_request)

        params, _, _, _ = await convert_to_general_agent_params(request, [])
        assert params.session_recording is None

    @pytest.mark.asyncio
    async def test_session_recording_from_resolved_profile(self, base_request: dict):
        """session_recording stored in agent profile flows through resolver."""
        from app.services.agent.params.converter import convert_to_general_agent_params
        from app.services.agent.profile_resolver import ResolvedAgentProfile

        base_request["agent_id"] = "test-agent-with-recording"
        request = AgentRequest(**base_request)

        mock_profile = ResolvedAgentProfile(
            agent_id="test-agent-with-recording",
            skill_ids=(),
            mcp_ids=(),
            enabled_builtin_tools=("web_search",),
            system_prompt="",
            auto_restore_domains=(),
            engine_params={},
            session_recording="on_failure",
        )

        mock_resolver = AsyncMock()
        mock_resolver.resolve = AsyncMock(return_value=mock_profile)

        with patch(
            "app.services.agent.profile_resolver.get_agent_profile_resolver",
            return_value=mock_resolver,
        ):
            params, _, _, _ = await convert_to_general_agent_params(request, [])
            assert params.session_recording == "on_failure"


class TestSessionRecordingRequestParsing:
    """AgentConfigRequest correctly parses session_recording."""

    def test_camel_case_parsing(self):
        cfg = AgentConfigRequest(**{"sessionRecording": "on_failure"})
        assert cfg.session_recording == "on_failure"

    def test_snake_case_parsing(self):
        cfg = AgentConfigRequest(session_recording="always")
        assert cfg.session_recording == "always"

    def test_none_default(self):
        cfg = AgentConfigRequest()
        assert cfg.session_recording is None

    def test_validation_rejects_invalid(self):
        with pytest.raises(ValueError, match="session_recording must be one of"):
            AgentConfigRequest(session_recording="invalid_mode")
