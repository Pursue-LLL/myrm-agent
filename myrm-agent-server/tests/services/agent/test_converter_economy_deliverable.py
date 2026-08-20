"""Integration: builtin-economy deliverable discipline through convert_to_general_agent_params."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.ai_agents.prompts.deliverable_discipline import KNOWLEDGE_WORK_SYSTEM_PROMPT
from app.services.agent.params.converter import convert_to_general_agent_params
from app.services.agent.params.models import AgentRequest
from app.services.agent.profile.profile_resolver import ResolvedAgentProfile
from tests.api.agent.utils import get_model_selection


@pytest.fixture
def base_request() -> dict[str, object]:
    return {
        "message_id": "test-msg-economy-deliverable",
        "chat_id": "test-chat-economy-deliverable",
        "query": "Draft a one-page project brief from these notes",
        "model_selection": get_model_selection(),
        "action_mode": "agent",
        "agent_id": "builtin-economy",
    }


class TestEconomyDeliverableConverterIntegration:
    """Web chat request → converter must merge economy system_prompt into user_instructions."""

    @pytest.mark.asyncio
    async def test_economy_agent_injects_deliverable_discipline(self, base_request: dict[str, object]) -> None:
        request = AgentRequest(**base_request)

        mock_profile = ResolvedAgentProfile(
            agent_id="builtin-economy",
            skill_ids=(),
            mcp_ids=(),
            enabled_builtin_tools=("web_search", "kanban"),
            system_prompt=KNOWLEDGE_WORK_SYSTEM_PROMPT,
            auto_restore_domains=(),
            engine_params={},
        )
        mock_resolver = AsyncMock()
        mock_resolver.resolve = AsyncMock(return_value=mock_profile)

        from tests.api.agent.conftest import _build_mock_user_configs

        mock_configs = _build_mock_user_configs()
        with (
            patch(
                "app.services.agent.profile.profile_resolver.get_agent_profile_resolver",
                return_value=mock_resolver,
            ),
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                AsyncMock(return_value=mock_configs),
            ),
        ):
            params, _, _, _ = await convert_to_general_agent_params(request, [])

        assert params.user_instructions is not None
        assert "<deliverable_discipline>" in params.user_instructions
        assert "use the kanban board" in params.user_instructions
        assert "Do not describe file contents" in params.user_instructions
        assert KNOWLEDGE_WORK_SYSTEM_PROMPT in params.user_instructions
