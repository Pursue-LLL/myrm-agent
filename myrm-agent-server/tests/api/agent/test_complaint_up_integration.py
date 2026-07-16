"""Integration test: Complaint-up (regenerate → tier escalation) in converter.

Verifies that when a user clicks Regenerate (sibling_group_id present, no
regenerate_instruction), the converter correctly computes complaint_min_tier
and passes it to route_task.  Also verifies that regenerate-with-instruction
does NOT trigger escalation.

Mocks route_task to capture the min_tier argument without hitting a real LLM.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.llms.routing.complexity_router import (
    RoutingResult,
    RoutingTier,
)

from app.core.types import ModelConfig
from app.services.agent.params.models import AgentRequest
from tests.api.agent.utils import get_model_selection

_DUMMY_KEY = "sk-test-routing"


def _lite_selection() -> dict[str, object]:
    return {"providerId": "openai", "model": "gpt-4o-mini"}


def _reasoning_selection() -> dict[str, object]:
    return {"providerId": "openai", "model": "o1-preview"}


def _make_routing_result(tier: RoutingTier = RoutingTier.STANDARD) -> RoutingResult:
    return RoutingResult(
        tier=tier,
        model_cfg=ModelConfig(model="gpt-4o", api_key=_DUMMY_KEY),
        fallback_model_cfg=None,
        reason="test",
    )


@pytest.fixture
def base_request() -> dict[str, object]:
    return {
        "message_id": "test-msg-complaint",
        "chat_id": "test-chat-complaint",
        "query": "hello",
        "model_selection": get_model_selection(),
        "light_model_selection": _lite_selection(),
        "reasoning_model_selection": _reasoning_selection(),
    }


class TestComplaintUpEscalation:
    """converter.py correctly escalates tier on complaint-up regenerates."""

    @pytest.mark.asyncio
    async def test_complaint_up_escalates_with_simple_history(self, base_request: dict[str, object]) -> None:
        """sibling_group_id + no instruction + last tier SIMPLE → min_tier STANDARD."""
        base_request["sibling_group_id"] = "sg-test-1"
        request = AgentRequest(**base_request)

        mock_route = AsyncMock(return_value=_make_routing_result(RoutingTier.STANDARD))

        with (
            patch(
                "myrm_agent_harness.toolkits.llms.routing.complexity_router.route_task",
                mock_route,
            ),
            patch(
                "app.database.repositories.chat_repo.ChatRepository.get_recent_routing_tiers",
                new_callable=AsyncMock,
                return_value=["simple"],
            ),
            patch(
                "myrm_agent_harness.toolkits.llms.routing.complexity_router.record_misroute",
            ) as mock_misroute,
        ):
            from app.services.agent.params.converter import convert_to_general_agent_params

            _, routing_tier, _, _ = await convert_to_general_agent_params(request, [])

        assert mock_route.call_count == 1
        call_kwargs = mock_route.call_args
        assert call_kwargs.kwargs.get("min_tier") == RoutingTier.STANDARD
        mock_misroute.assert_called_once_with(RoutingTier.SIMPLE)

    @pytest.mark.asyncio
    async def test_complaint_up_escalates_standard_to_reasoning(self, base_request: dict[str, object]) -> None:
        """sibling_group_id + no instruction + last tier STANDARD → min_tier REASONING."""
        base_request["sibling_group_id"] = "sg-test-2"
        request = AgentRequest(**base_request)

        mock_route = AsyncMock(return_value=_make_routing_result(RoutingTier.REASONING))

        with (
            patch(
                "myrm_agent_harness.toolkits.llms.routing.complexity_router.route_task",
                mock_route,
            ),
            patch(
                "app.database.repositories.chat_repo.ChatRepository.get_recent_routing_tiers",
                new_callable=AsyncMock,
                return_value=["standard"],
            ),
            patch(
                "myrm_agent_harness.toolkits.llms.routing.complexity_router.record_misroute",
            ) as mock_misroute,
        ):
            from app.services.agent.params.converter import convert_to_general_agent_params

            await convert_to_general_agent_params(request, [])

        call_kwargs = mock_route.call_args
        assert call_kwargs.kwargs.get("min_tier") == RoutingTier.REASONING
        mock_misroute.assert_called_once_with(RoutingTier.STANDARD)

    @pytest.mark.asyncio
    async def test_complaint_up_no_history_defaults_standard(self, base_request: dict[str, object]) -> None:
        """sibling_group_id + no instruction + no history → min_tier STANDARD (safe default)."""
        base_request["sibling_group_id"] = "sg-test-3"
        request = AgentRequest(**base_request)

        mock_route = AsyncMock(return_value=_make_routing_result(RoutingTier.STANDARD))

        with (
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

        call_kwargs = mock_route.call_args
        assert call_kwargs.kwargs.get("min_tier") == RoutingTier.STANDARD

    @pytest.mark.asyncio
    async def test_regenerate_with_instruction_no_escalation(self, base_request: dict[str, object]) -> None:
        """sibling_group_id + WITH instruction → no complaint-up, min_tier stays None."""
        base_request["sibling_group_id"] = "sg-test-4"
        base_request["regenerate_instruction"] = "Use a more formal tone"
        request = AgentRequest(**base_request)

        mock_route = AsyncMock(return_value=_make_routing_result(RoutingTier.STANDARD))

        with (
            patch(
                "myrm_agent_harness.toolkits.llms.routing.complexity_router.route_task",
                mock_route,
            ),
            patch(
                "app.database.repositories.chat_repo.ChatRepository.get_recent_routing_tiers",
                new_callable=AsyncMock,
                return_value=["simple"],
            ),
        ):
            from app.services.agent.params.converter import convert_to_general_agent_params

            await convert_to_general_agent_params(request, [])

        call_kwargs = mock_route.call_args
        assert call_kwargs.kwargs.get("min_tier") is None
