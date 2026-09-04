"""Tests for AgentRequest session_knowledge_base_ids converter integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
import pytest

from app.services.agent.params.converter import convert_to_general_agent_params
from app.services.agent.params.models import AgentRequest


class TestConverterSessionKnowledgeBaseIntegration:
    @pytest.mark.asyncio
    async def test_converter_merges_explicit_session_knowledge_base_ids(
        self,
        base_request: dict,
    ) -> None:
        base_request["session_knowledge_base_ids"] = [
            "kb-custom-handbook",
            "kb-engineering-standard",
        ]
        request = AgentRequest(**base_request)

        with (
            patch(
                "app.services.memory.shared_context.shared_context.resolve_shared_context_ids",
                AsyncMock(return_value=["kb-default-profile"]),
            ),
            patch(
                "app.services.memory.shared_context.shared_context.SharedContextService.get_context_names",
                AsyncMock(return_value={"kb-custom-handbook": "Custom Handbook"}),
            ),
        ):
            params, *rest = await convert_to_general_agent_params(request, [])

            # Both profile-resolved shared contexts and explicit session-mounted knowledge bases are merged
            assert "kb-default-profile" in params.memory_shared_context_ids
            assert "kb-custom-handbook" in params.memory_shared_context_ids
            assert "kb-engineering-standard" in params.memory_shared_context_ids
            assert len(params.memory_shared_context_ids) == 3
