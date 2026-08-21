"""Integration and unit tests for cross-vendor task specialty routing in converter.

Verifies:
1. When code_model_selection or long_doc_model_selection is provided and query hits specialty keywords,
   converter routes to specialty model and sets routing_tier appropriately.
2. When query hits specialty but no specialty model is configured, it falls open cleanly to complexity routing.
3. Fallback specialty model config is properly resolved and attached.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.llms.routing.complexity_router import (
    RoutingResult,
    RoutingTier,
)
from myrm_agent_harness.toolkits.llms.routing.specialty_router import TaskSpecialty

from app.core.types import ModelConfig
from app.services.agent.params.models import AgentRequest, ModelSelection
from tests.api.agent.utils import get_model_selection

_DUMMY_KEY = "sk-test-specialty-routing"


def _selection(provider: str, model: str) -> dict[str, object]:
    return {"providerId": provider, "model": model}


@pytest.fixture
def base_request_data() -> dict[str, object]:
    return {
        "message_id": "test-msg-spec",
        "chat_id": "test-chat-spec",
        "query": "Please optimize this Python function: def calculate(): pass",
        "model_selection": get_model_selection(),
        "code_model_selection": _selection("anthropic", "claude-3-7-sonnet-20250219"),
        "fallback_code_model_selection": _selection("deepseek", "deepseek-coder"),
        "long_doc_model_selection": _selection("google", "gemini-1.5-pro"),
    }


async def _fake_resolve(selection: ModelSelection, providers: dict[str, object] | None) -> ModelConfig:
    return ModelConfig(
        model=selection.model or "default-model",
        api_key=_DUMMY_KEY,
    )


class TestTaskSpecialtyRoutingIntegration:
    """Converter correctly resolves specialty model slots and routes matching tasks."""

    @pytest.mark.asyncio
    async def test_code_specialty_routing_applied(self, base_request_data: dict[str, object]) -> None:
        request = AgentRequest(**base_request_data)

        with (
            patch(
                "app.services.agent.params.converter._resolve_model_config",
                new=_fake_resolve,
            ),
            patch(
                "app.database.repositories.chat_repo.ChatRepository.get_recent_routing_tiers",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            from app.services.agent.params.converter import convert_to_general_agent_params

            params, routing_tier, warnings, _ = await convert_to_general_agent_params(request, [])

        assert params.model == "claude-3-7-sonnet-20250219"
        assert params.fallback_model == "deepseek-coder"
        assert routing_tier == "code"

    @pytest.mark.asyncio
    async def test_long_doc_specialty_routing_applied(self, base_request_data: dict[str, object]) -> None:
        base_request_data["query"] = "Please summarize this full transcript document: " + "word " * 500
        request = AgentRequest(**base_request_data)

        with (
            patch(
                "app.services.agent.params.converter._resolve_model_config",
                new=_fake_resolve,
            ),
            patch(
                "app.database.repositories.chat_repo.ChatRepository.get_recent_routing_tiers",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            from app.services.agent.params.converter import convert_to_general_agent_params

            params, routing_tier, warnings, _ = await convert_to_general_agent_params(request, [])

        assert params.model == "gemini-1.5-pro"
        assert routing_tier == "long_doc"

    @pytest.mark.asyncio
    async def test_fail_open_to_complexity_router_when_no_specialty_configured(
        self, base_request_data: dict[str, object]
    ) -> None:
        # Clear specialty slots
        del base_request_data["code_model_selection"]
        del base_request_data["fallback_code_model_selection"]
        del base_request_data["long_doc_model_selection"]
        request = AgentRequest(**base_request_data)

        with (
            patch(
                "app.services.agent.params.converter._resolve_model_config",
                new=_fake_resolve,
            ),
            patch(
                "app.database.repositories.chat_repo.ChatRepository.get_recent_routing_tiers",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            from app.services.agent.params.converter import convert_to_general_agent_params

            params, routing_tier, warnings, _ = await convert_to_general_agent_params(request, [])

        # Should fall open to default model_selection
        assert routing_tier in ("standard", "reasoning", "simple")
