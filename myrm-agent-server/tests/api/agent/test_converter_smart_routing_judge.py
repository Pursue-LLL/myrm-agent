"""Integration: smart-routing LLM judge creation path in converter.

Verifies the judge LLM is actually created via ``get_llm_from_config`` and
forwarded to ``route_task`` — guarding the TypeError regression where the
config object was passed as a positional string (``(cfg, "api_keys", None)``),
which silently disabled the LLM-judge phase of smart routing.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.llms.routing.complexity_router import (
    RoutingResult,
    RoutingTier,
)

from app.core.types import ModelConfig
from app.services.agent.params.models import AgentRequest, ModelSelection
from tests.api.agent.utils import get_model_selection

_DUMMY_KEY = "sk-test-routing"


def _lite_selection() -> dict[str, object]:
    return {"providerId": "openai", "model": "gpt-4o-mini"}


@pytest.fixture
def base_request() -> dict[str, object]:
    return {
        "message_id": "test-msg-judge",
        "chat_id": "test-chat-judge",
        "query": "hello",
        "model_selection": get_model_selection(),
        "lite_model_selection": _lite_selection(),
        "light_model_selection": _lite_selection(),
        "reasoning_model_selection": _lite_selection(),
    }


async def _fake_resolve(
    selection: ModelSelection, providers: dict[str, object] | None
) -> ModelConfig:
    return ModelConfig(model="gpt-4o-mini", api_key=_DUMMY_KEY)


def _fake_route_result() -> RoutingResult:
    return RoutingResult(
        tier=RoutingTier.STANDARD,
        model_cfg=ModelConfig(model="gpt-4o-mini", api_key=_DUMMY_KEY),
        fallback_model_cfg=None,
        reason="rule_based",
    )


class TestSmartRoutingJudgeCreation:
    """converter correctly creates the judge LLM and passes it to route_task."""

    @pytest.mark.asyncio
    async def test_judge_llm_created_and_passed_to_route_task(
        self, base_request: dict[str, object]
    ) -> None:
        request = AgentRequest(**base_request)
        fake_judge = AsyncMock()
        mock_route = AsyncMock(return_value=_fake_route_result())

        with (
            patch(
                "app.services.agent.params.converter._resolve_model_config",
                new=_fake_resolve,
            ),
            patch(
                "myrm_agent_harness.toolkits.llms.core.manager.LLMManager.get_llm_from_config",
                new_callable=AsyncMock,
                return_value=fake_judge,
            ) as mock_get_llm,
            patch(
                "myrm_agent_harness.toolkits.llms.routing.complexity_router.route_task",
                mock_route,
            ),
            patch(
                "app.database.repositories.chat_repo.ChatRepository.get_recent_routing_tiers",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            from app.services.agent.params.converter import convert_to_general_agent_params

            await convert_to_general_agent_params(request, [])

        assert mock_get_llm.call_count == 1
        args = mock_get_llm.call_args
        assert args is not None
        assert len(args.args) == 1 and args.args[0] is not None
        assert args.kwargs == {}

        assert mock_route.call_count == 1
        assert mock_route.call_args.kwargs["judge_llm"] is fake_judge

    @pytest.mark.asyncio
    async def test_no_lite_model_selection_skips_judge(
        self, base_request: dict[str, object]
    ) -> None:
        del base_request["lite_model_selection"]
        request = AgentRequest(**base_request)
        mock_route = AsyncMock(return_value=_fake_route_result())

        with (
            patch(
                "app.services.agent.params.converter._resolve_model_config",
                new=_fake_resolve,
            ),
            patch(
                "myrm_agent_harness.toolkits.llms.core.manager.LLMManager.get_llm_from_config",
                new_callable=AsyncMock,
            ) as mock_get_llm,
            patch(
                "myrm_agent_harness.toolkits.llms.routing.complexity_router.route_task",
                mock_route,
            ),
            patch(
                "app.database.repositories.chat_repo.ChatRepository.get_recent_routing_tiers",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            from app.services.agent.params.converter import convert_to_general_agent_params

            await convert_to_general_agent_params(request, [])

        mock_get_llm.assert_not_called()
        assert mock_route.call_args.kwargs["judge_llm"] is None
