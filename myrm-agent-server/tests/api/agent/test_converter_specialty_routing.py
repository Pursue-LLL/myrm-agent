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
            from app.services.agent.params.converter import (
                convert_to_general_agent_params,
            )

            params, routing_tier, specialty, routing_reason, warnings, _ = await convert_to_general_agent_params(request, [])

        assert params.model_cfg.model == "claude-3-7-sonnet-20250219"
        assert params.fallback_model_cfg.model == "deepseek-coder"
        assert routing_tier == "code"
        assert specialty == "code"

    @pytest.mark.asyncio
    async def test_long_doc_specialty_routing_applied(self, base_request_data: dict[str, object]) -> None:
        base_request_data["query"] = "请帮我总结这份全文长文档与整份报告内容: " + "word " * 500
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

            params, routing_tier, specialty, routing_reason, warnings, _ = await convert_to_general_agent_params(request, [])

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
        base_request_data["reasoning_model_selection"] = _selection("deepseek", "deepseek-reasoner")
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

            params, routing_tier, specialty, routing_reason, warnings, _ = await convert_to_general_agent_params(request, [])

        # Should fall open to complexity router
        assert routing_tier in ("standard", "reasoning", "simple")


class TestSpecialtyRoutingSSEChunkEmission:
    """Verifies that generate_cancellable_stream correctly yields routing_decision SSE chunk with specialty."""

    @pytest.mark.asyncio
    async def test_specialty_in_routing_decision_sse_event(self) -> None:
        import json

        from app.ai_agents.agents import GeneralAgentParams
        from app.services.agent.stream_session.stream_chunks import (
            generate_cancellable_stream,
        )
        from app.services.agent.stream_session.stream_session_types import (
            AgentStreamSession,
        )
        from app.services.agent.streaming_support.stream_collector import (
            StreamContentCollector,
        )

        params = GeneralAgentParams(
            message_id="msg-spec-123",
            chat_id="chat-spec-456",
            query="def solve(): pass",
            model_cfg=ModelConfig(model="claude-3-7-sonnet", api_key="sk-test"),
        )
        fake_request = AgentRequest(
            message_id="msg-spec-123",
            chat_id="chat-spec-456",
            query="def solve(): pass",
            model_selection=get_model_selection(),
        )
        monitor_mock = AsyncMock()
        monitor_mock.start = AsyncMock()
        session = AgentStreamSession(
            request=fake_request,
            http_request=None,  # type: ignore[arg-type]
            params=params,
            cancel_token=None,  # type: ignore[arg-type]
            steering_token=None,
            routing_tier="code",
            archive_restore_results=[],
            research_model_cfg=None,
            registry=None,
            collector=StreamContentCollector(chat_id="chat-spec-456"),
            monitor=monitor_mock,
            is_long_running_task=False,
            goal_provider=None,
            extra_context={},
            routing_specialty="code",
        )

        with (
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.services.agent.stream_session.migration_readiness_preflight.resolve_and_build_migration_readiness_gap_sse_event",
                new_callable=AsyncMock,
                return_value=(None, None),
            ),
            patch("app.services.agent.stream_session.stream_chunks.iter_agent_stream_chunks") as mock_iter,
            patch("app.services.agent.stream_session.stream_chunks.finalize_agent_stream_session"),
        ):

            async def _empty_iter(*args, **kwargs):
                if False:
                    yield ""

            mock_iter.side_effect = _empty_iter

            chunks = []
            async for chunk in generate_cancellable_stream(session):
                chunks.append(chunk)

        # First chunk should be routing_decision
        routing_chunks = [c for c in chunks if "routing_decision" in c]
        assert len(routing_chunks) == 1
        lines = routing_chunks[0].strip().split("\n")
        data_line = next(line for line in lines if line.startswith("data: "))
        event_data = json.loads(data_line[6:])
        assert event_data["type"] == "routing_decision"
        assert event_data["messageId"] == "msg-spec-123"
        assert event_data["data"]["tier"] == "code"
        assert event_data["data"]["specialty"] == "code"


class TestAutoMoAOverlayGateConverter:
    """Verifies that convert_to_general_agent_params activates MoA overlay when routed to REASONING."""

    @pytest.mark.asyncio
    async def test_auto_moa_activation_on_reasoning_tier(self, base_request_data: dict[str, object]) -> None:
        del base_request_data["code_model_selection"]
        del base_request_data["fallback_code_model_selection"]
        del base_request_data["long_doc_model_selection"]
        base_request_data["light_model_selection"] = _selection("openai", "gpt-4o-mini")
        base_request_data["reasoning_model_selection"] = _selection("deepseek", "deepseek-reasoner")
        base_request_data["auto_moa_reasoning"] = True
        base_request_data["engine_params"] = {
            "moa_overlay": {
                "enabled": True,
                "presets": {
                    "review": {
                        "reference_model_selections": [
                            {"providerId": "anthropic", "model": "claude-3-5-sonnet"},
                        ],
                    },
                },
            },
        }
        base_request_data["action_mode"] = "agent"
        # A mathematical proof query with math symbols and keywords to trigger reasoning tier
        base_request_data["query"] = r"Please prove the following theorem step by step: \sum_{k=1}^n k = \frac{n(n+1)}{2}"
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

            params, routing_tier, specialty, routing_reason, warnings, _ = await convert_to_general_agent_params(request, [])

        assert routing_tier == "reasoning"
        assert params.engine_params is not None
        overlay = params.engine_params.get("moa_overlay")
        assert isinstance(overlay, dict)
        assert overlay.get("enabled") is True
        assert overlay.get("reference_reasoning_effort") == "high"
        refs = overlay.get("reference_model_selections")
        assert isinstance(refs, list)
        assert refs[0]["model"] == "claude-3-5-sonnet"
