"""Integration test: Complaint-up (regenerate → tier escalation) in converter.

Verifies that when a user clicks Regenerate (sibling_group_id present, no
regenerate_instruction), the converter correctly computes complaint_min_tier
and passes it to route_task.  Also verifies that regenerate-with-instruction
does NOT trigger escalation, is forwarded as guidance, and that every routing
decision logs its latency.

Mocks route_task to capture the min_tier argument without hitting a real LLM.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from contextlib import AbstractContextManager
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


def _reasoning_selection() -> dict[str, object]:
    return {"providerId": "openai", "model": "o1-preview"}


def _make_routing_result(tier: RoutingTier = RoutingTier.STANDARD) -> RoutingResult:
    return RoutingResult(
        tier=tier,
        model_cfg=ModelConfig(model="gpt-4o", api_key=_DUMMY_KEY),
        fallback_model_cfg=None,
        reason="test",
    )


async def _resolve_without_provider_keys(selection: ModelSelection, providers: dict[str, object] | None) -> ModelConfig:
    return ModelConfig(model=selection.model, api_key=_DUMMY_KEY)


def _last_turn_tier(tier: str | None) -> AbstractContextManager[AsyncMock]:
    """The tier the retried answer turn recorded, as read when a retry computes its floor."""
    return patch(
        "app.database.repositories.chat_repo.ChatRepository.get_last_turn_routing_tier",
        new_callable=AsyncMock,
        return_value=tier,
    )


@pytest.fixture(autouse=True)
def _resolvable_slots() -> Iterator[None]:
    """Slot models resolve to distinct configs, so the retry ladder has different rungs to climb to."""
    with patch("app.services.agent.params.converter._resolve_model_config", new=_resolve_without_provider_keys):
        yield


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
        request = AgentRequest.model_validate(base_request)

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
            _last_turn_tier("simple"),
        ):
            from app.services.agent.params.converter import (
                convert_to_general_agent_params,
            )

            params, routing_tier, *rest = await convert_to_general_agent_params(request, [])

        assert mock_route.call_count == 1
        call_kwargs = mock_route.call_args
        assert call_kwargs.kwargs.get("min_tier") == RoutingTier.STANDARD
        assert "Regeneration guidance" not in (params.user_instructions or "")

    @pytest.mark.asyncio
    async def test_complaint_up_escalates_standard_to_reasoning(self, base_request: dict[str, object]) -> None:
        """sibling_group_id + no instruction + last tier STANDARD → min_tier REASONING."""
        base_request["sibling_group_id"] = "sg-test-2"
        request = AgentRequest.model_validate(base_request)

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
            _last_turn_tier("standard"),
        ):
            from app.services.agent.params.converter import (
                convert_to_general_agent_params,
            )

            await convert_to_general_agent_params(request, [])

        call_kwargs = mock_route.call_args
        assert call_kwargs.kwargs.get("min_tier") == RoutingTier.REASONING

    @pytest.mark.asyncio
    async def test_complaint_up_reasoning_keeps_reasoning_floor(self, base_request: dict[str, object]) -> None:
        """sibling_group_id + no instruction + last tier REASONING → min_tier stays
        REASONING (the highest tier has nothing to escalate to)."""
        base_request["sibling_group_id"] = "sg-test-5"
        request = AgentRequest.model_validate(base_request)

        mock_route = AsyncMock(return_value=_make_routing_result(RoutingTier.REASONING))

        with (
            patch(
                "myrm_agent_harness.toolkits.llms.routing.complexity_router.route_task",
                mock_route,
            ),
            patch(
                "app.database.repositories.chat_repo.ChatRepository.get_recent_routing_tiers",
                new_callable=AsyncMock,
                return_value=["reasoning"],
            ),
            _last_turn_tier("reasoning"),
        ):
            from app.services.agent.params.converter import (
                convert_to_general_agent_params,
            )

            await convert_to_general_agent_params(request, [])

        call_kwargs = mock_route.call_args
        assert call_kwargs.kwargs.get("min_tier") == RoutingTier.REASONING

    @pytest.mark.asyncio
    async def test_complaint_up_unrecorded_answer_climbs_from_the_main_model(self, base_request: dict[str, object]) -> None:
        """sibling_group_id + no instruction + no recorded tier → the answer ran the main model, so min_tier REASONING."""
        base_request["sibling_group_id"] = "sg-test-3"
        request = AgentRequest.model_validate(base_request)

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
            _last_turn_tier(None),
        ):
            from app.services.agent.params.converter import (
                convert_to_general_agent_params,
            )

            await convert_to_general_agent_params(request, [])

        call_kwargs = mock_route.call_args
        assert call_kwargs.kwargs.get("min_tier") == RoutingTier.REASONING

    @pytest.mark.asyncio
    @pytest.mark.parametrize("action_mode", ["fast", "agent"])
    async def test_regenerate_with_instruction_no_escalation(self, base_request: dict[str, object], action_mode: str) -> None:
        """sibling_group_id + WITH instruction → no escalation; the instruction reaches the prompt in every mode."""
        base_request["action_mode"] = action_mode
        base_request["sibling_group_id"] = "sg-test-4"
        base_request["regenerate_instruction"] = "Use a more formal tone"
        request = AgentRequest.model_validate(base_request)

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
            _last_turn_tier("simple") as baseline_lookup,
        ):
            from app.services.agent.params.converter import (
                convert_to_general_agent_params,
            )

            params, *_ = await convert_to_general_agent_params(request, [])

        baseline_lookup.assert_not_awaited()
        call_kwargs = mock_route.call_args
        assert call_kwargs.kwargs.get("min_tier") is None
        assert "[Regeneration guidance: Use a more formal tone]" in (params.user_instructions or "")


class TestSmartRoutingLog:
    """Every routing decision is logged with its own latency."""

    @pytest.mark.asyncio
    async def test_decision_log_carries_routing_latency(
        self, base_request: dict[str, object], caplog: pytest.LogCaptureFixture
    ) -> None:
        request = AgentRequest.model_validate(base_request)
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
            caplog.at_level(logging.INFO, logger="app.services.agent.params.converter"),
        ):
            from app.services.agent.params.converter import (
                convert_to_general_agent_params,
            )

            await convert_to_general_agent_params(request, [])

        decisions = [record.getMessage() for record in caplog.records if record.getMessage().startswith("Smart routing:")]
        assert len(decisions) == 1
        assert re.search(r"tier=standard model=gpt-4o reason=test routing_ms=\d+\.\d$", decisions[0])
