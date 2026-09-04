"""Integration and unit tests for AgentRequest session_knowledge_base_ids converter integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.types import ModelConfig
from app.services.agent.params.converter import convert_to_general_agent_params
from app.services.agent.params.models import AgentRequest, ModelSelection
from tests.api.agent.utils import get_model_selection

_DUMMY_KEY = "sk-test-kb-key"


async def _fake_resolve(selection: ModelSelection, providers: dict[str, object] | None) -> ModelConfig:
    return ModelConfig(
        model=selection.model or "default-model",
        api_key=_DUMMY_KEY,
    )


@pytest.fixture
def base_request_data() -> dict[str, object]:
    return {
        "message_id": "test-msg-kb",
        "chat_id": "test-chat-kb",
        "query": "Please summarize our company architectural guidelines and coding standards.",
        "model_selection": get_model_selection(),
    }


class TestConverterSessionKnowledgeBaseIntegration:
    @pytest.mark.asyncio
    async def test_converter_merges_explicit_session_knowledge_base_ids(
        self,
        base_request_data: dict[str, object],
    ) -> None:
        base_request_data["session_knowledge_base_ids"] = [
            "kb-custom-handbook",
            "kb-engineering-standard",
        ]
        request = AgentRequest(**base_request_data)

        with (
            patch(
                "app.services.agent.params.converter._resolve_model_config",
                new=_fake_resolve,
            ),
            patch(
                "app.services.memory.shared_context.shared_context.resolve_shared_context_ids",
                new_callable=AsyncMock,
                return_value=["kb-default-profile"],
            ),
            patch(
                "app.services.memory.shared_context.shared_context.SharedContextService.get_context_names",
                new_callable=AsyncMock,
                return_value={"kb-custom-handbook": "Custom Handbook"},
            ),
            patch(
                "app.database.repositories.chat_repo.ChatRepository.get_recent_routing_tiers",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            params, *rest = await convert_to_general_agent_params(request, [])

            # Both profile-resolved shared contexts and explicit session-mounted knowledge bases are merged
            assert "kb-default-profile" in params.memory_shared_context_ids
            assert "kb-custom-handbook" in params.memory_shared_context_ids
            assert "kb-engineering-standard" in params.memory_shared_context_ids
            assert len(params.memory_shared_context_ids) == 3
