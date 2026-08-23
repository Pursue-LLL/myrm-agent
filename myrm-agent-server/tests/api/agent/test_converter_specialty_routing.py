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


async def _fake_resolve(
    selection: ModelSelection, providers: dict[str, object] | None
) -> ModelConfig:
    return ModelConfig(
        model=selection.model or "default-model",
        api_key=_DUMMY_KEY,
    )


class TestTaskSpecialtyRoutingIntegration:
    """Converter correctly resolves specialty model slots and routes matching tasks."""

    @pytest.mark.asyncio
    async def test_code_specialty_routing_applied(
        self, base_request_data: dict[str, object]
    ) -> None:
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
            from app.services.agent.params.converter import (
                convert_to_general_agent_params,
            )

            params, routing_tier, specialty, warnings, _ = (
                await convert_to_general_agent_params(request, [])
            )

        assert params.model_cfg.model == "claude-3-7-sonnet-20250219"
        assert params.fallback_model_cfg.model == "deepseek-coder"
        assert routing_tier == "code"
        assert specialty == "code"

    @pytest.mark.asyncio
    async def test_long_doc_specialty_routing_applied(
        self, base_request_data: dict[str, object]
    ) -> None:
        base_request_data["query"] = (
            "请帮我总结这份全文长文档与整份报告内容: " + "word " * 500
        )
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
            from app.services.agent.params.converter import (
                convert_to_general_agent_params,
            )

            params, routing_tier, specialty, warnings, _ = (
                await convert_to_general_agent_params(request, [])
            )

        assert params.model_cfg.model == "gemini-1.5-pro"
        assert routing_tier == "long_doc"
        assert specialty == "long_doc"

    @pytest.mark.asyncio
    async def test_fail_open_to_complexity_router_when_no_specialty_configured(
        self, base_request_data: dict[str, object]
    ) -> None:
        # Clear specialty slots and add light/reasoning slots to enable complexity routing
        del base_request_data["code_model_selection"]
        del base_request_data["fallback_code_model_selection"]
        del base_request_data["long_doc_model_selection"]
        base_request_data["light_model_selection"] = _selection("openai", "gpt-4o-mini")
        base_request_data["reasoning_model_selection"] = _selection(
            "deepseek", "deepseek-reasoner"
        )
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
            from app.services.agent.params.converter import (
                convert_to_general_agent_params,
            )

            params, routing_tier, specialty, warnings, _ = (
                await convert_to_general_agent_params(request, [])
            )

        # Should fall open to complexity router
        assert routing_tier in ("standard", "reasoning", "simple")


class TestSpecialtyRoutingSSEChunkEmission:
    """Verifies that generate_cancellable_stream correctly yields routing_decision SSE chunk with specialty."""

    @pytest.mark.asyncio
    async def test_specialty_in_routing_decision_sse_event(self) -> None:
        import json
        from app.ai_agents.agents import GeneralAgentParams
        from app.services.agent.stream_session.stream_session_types import (
            AgentStreamSession,
        )
        from app.services.agent.stream_session.stream_chunks import (
            generate_cancellable_stream,
        )
        from app.services.agent.streaming_support.stream_collector import (
            StreamEventCollector,
        )

        params = GeneralAgentParams(
            message_id="msg-spec-123",
            chat_id="chat-spec-456",
            query="def solve(): pass",
            model_cfg=ModelConfig(model="claude-3-7-sonnet", api_key="sk-test"),
        )
        session = AgentStreamSession(
            params=params,
            collector=StreamEventCollector(
                message_id="msg-spec-123", chat_id="chat-spec-456"
            ),
            routing_tier="code",
            routing_specialty="code",
        )

        with patch(
            "app.services.agent.stream_session.stream_chunks.iter_agent_stream_chunks"
        ) as mock_iter:

            async def _empty_iter(*args, **kwargs):
                if False:
                    yield ""

            mock_iter.side_effect = _empty_iter

            with patch(
                "app.services.agent.stream_session.stream_chunks.finalize_agent_stream_session"
            ):
                chunks = []
                async for chunk in generate_cancellable_stream(session):
                    chunks.append(chunk)

        # First chunk should be routing_decision
        routing_chunks = [c for c in chunks if "routing_decision" in c]
        assert len(routing_chunks) == 1
        lines = routing_chunks[0].strip().split("\n")
        data_line = next(l for l in lines if l.startswith("data: "))
        event_data = json.loads(data_line[6:])
        assert event_data["type"] == "routing_decision"
        assert event_data["messageId"] == "msg-spec-123"
        assert event_data["data"]["tier"] == "code"
        assert event_data["data"]["specialty"] == "code"
