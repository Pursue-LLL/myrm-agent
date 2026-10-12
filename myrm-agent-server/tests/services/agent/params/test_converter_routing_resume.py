"""Smart Routing across requests of one chat: HITL resume continuity and routing-history wiring.

A resume request (tool approval, plan confirmation) carries the main model selection only, so the converter must
continue the interrupted turn on the model that turn was routed to instead of re-routing an empty query.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.llms.routing.complexity_router import RoutingResult, RoutingTier

from app.core.types import ModelConfig
from app.services.agent.params import routing_memory
from app.services.agent.params.converter import convert_to_general_agent_params
from app.services.agent.params.models import AgentRequest, ModelSelection
from app.services.agent.params.routing_memory import remember_turn_routing

_MAIN = {"providerId": "openai", "model": "gpt-4o"}
_LIGHT = {"providerId": "openai", "model": "gpt-4o-mini"}
_REASONING = {"providerId": "deepseek", "model": "deepseek-reasoner"}
_CODE = {"providerId": "anthropic", "model": "claude-3-7-sonnet-20250219"}
_CODE_FALLBACK = {"providerId": "deepseek", "model": "deepseek-coder"}
_CODE_QUERY = "Please optimize this Python function: def calculate(): pass"
_MATH_QUERY = r"Please prove the following theorem step by step: \sum_{k=1}^n k = \frac{n(n+1)}{2}"
_RESUME_VALUE: dict[str, object] = {"decision": "approve"}


async def _fake_resolve(selection: ModelSelection, providers: dict[str, object] | None) -> ModelConfig:
    return ModelConfig(model=selection.model, api_key="sk-test-routing-resume")


def _turn(**overrides: object) -> AgentRequest:
    payload: dict[str, object] = {
        "message_id": "msg-resume",
        "chat_id": "chat-resume",
        "query": "hello",
        "model_selection": _MAIN,
    }
    payload.update(overrides)
    return AgentRequest(**payload)


def _resume(**overrides: object) -> AgentRequest:
    return _turn(query="", resume_value=_RESUME_VALUE, **overrides)


@asynccontextmanager
async def _converter_env(recent: list[str] | None = None) -> AsyncIterator[None]:
    with (
        patch("app.services.agent.params.converter._resolve_model_config", new=_fake_resolve),
        patch(
            "app.database.repositories.chat_repo.ChatRepository.get_recent_routing_tiers",
            new_callable=AsyncMock,
            return_value=recent or [],
        ),
    ):
        yield


@pytest.fixture(autouse=True)
def _isolated_memory() -> Iterator[None]:
    routing_memory._turns.clear()
    yield
    routing_memory._turns.clear()


async def _convert(request: AgentRequest):
    params, tier, specialty, reason, _warnings, _archive = await convert_to_general_agent_params(request, [])
    return params, tier, specialty, reason


class TestResumeContinuesOnTheRoutedModel:
    async def test_code_specialty_turn_resumes_on_the_code_model(self) -> None:
        turn = _turn(
            query=_CODE_QUERY,
            code_model_selection=_CODE,
            fallback_code_model_selection=_CODE_FALLBACK,
        )
        async with _converter_env():
            params, tier, specialty, reason = await _convert(turn)
            assert params.model_cfg.model == "claude-3-7-sonnet-20250219"
            remember_turn_routing(turn, tier=tier, specialty=specialty, reason=reason)

            resumed_params, resumed_tier, resumed_specialty, resumed_reason = await _convert(_resume())

        assert resumed_params.model_cfg.model == "claude-3-7-sonnet-20250219"
        assert resumed_params.fallback_model_cfg is not None
        assert resumed_params.fallback_model_cfg.model == "deepseek-coder"
        assert (resumed_tier, resumed_specialty, resumed_reason) == (tier, specialty, reason)

    async def test_reasoning_tier_turn_resumes_on_the_reasoning_model(self) -> None:
        turn = _turn(query=_MATH_QUERY, light_model_selection=_LIGHT, reasoning_model_selection=_REASONING)
        async with _converter_env():
            params, tier, specialty, reason = await _convert(turn)
            assert (params.model_cfg.model, tier) == ("deepseek-reasoner", "reasoning")
            remember_turn_routing(turn, tier=tier, specialty=specialty, reason=reason)

            resumed_params, resumed_tier, _, resumed_reason = await _convert(_resume())

        assert resumed_params.model_cfg.model == "deepseek-reasoner"
        assert (resumed_tier, resumed_reason) == ("reasoning", reason)

    async def test_resume_with_routing_slots_does_not_reroute_the_empty_query(self) -> None:
        turn = _turn(query=_MATH_QUERY, light_model_selection=_LIGHT, reasoning_model_selection=_REASONING)
        async with _converter_env():
            _, tier, specialty, reason = await _convert(turn)
            remember_turn_routing(turn, tier=tier, specialty=specialty, reason=reason)

            resumed_params, resumed_tier, _, _ = await _convert(
                _resume(light_model_selection=_LIGHT, reasoning_model_selection=_REASONING)
            )

        assert resumed_params.model_cfg.model == "deepseek-reasoner"
        assert resumed_tier == "reasoning"

    async def test_resume_without_remembered_turn_uses_the_main_model(self) -> None:
        async with _converter_env():
            params, tier, specialty, reason = await _convert(_resume())

        assert params.model_cfg.model == "gpt-4o"
        assert (tier, specialty, reason) == (None, None, None)

    async def test_resume_after_the_user_switched_the_main_model_honours_the_new_selection(self) -> None:
        turn = _turn(query=_MATH_QUERY, light_model_selection=_LIGHT, reasoning_model_selection=_REASONING)
        async with _converter_env():
            _, tier, specialty, reason = await _convert(turn)
            remember_turn_routing(turn, tier=tier, specialty=specialty, reason=reason)

            params, resumed_tier, _, _ = await _convert(
                _resume(model_selection={"providerId": "anthropic", "model": "claude-opus"})
            )

        assert params.model_cfg.model == "claude-opus"
        assert resumed_tier is None

    async def test_unrouted_user_turn_after_a_routed_one_resumes_on_the_main_model(self) -> None:
        routed = _turn(query=_MATH_QUERY, light_model_selection=_LIGHT, reasoning_model_selection=_REASONING)
        unrouted = _turn(query="hello again")
        async with _converter_env():
            _, tier, specialty, reason = await _convert(routed)
            remember_turn_routing(routed, tier=tier, specialty=specialty, reason=reason)
            _, tier, specialty, reason = await _convert(unrouted)
            remember_turn_routing(unrouted, tier=tier, specialty=specialty, reason=reason)

            params, resumed_tier, _, _ = await _convert(_resume())

        assert params.model_cfg.model == "gpt-4o"
        assert resumed_tier is None

    async def test_non_resume_conversion_never_reads_or_writes_the_memory(self) -> None:
        """Prewarm and wakeup callers convert non-resume requests and must not disturb a pending resume."""
        turn = _turn(query=_MATH_QUERY, light_model_selection=_LIGHT, reasoning_model_selection=_REASONING)
        async with _converter_env():
            await _convert(turn)

        assert len(routing_memory._turns) == 0


class TestRoutingHistoryWiring:
    async def test_specialty_history_in_routing_tier_keeps_the_tier_momentum(self) -> None:
        turn = _turn(query="ok", light_model_selection=_LIGHT, reasoning_model_selection=_REASONING)
        routed = RoutingResult(
            tier=RoutingTier.STANDARD,
            model_cfg=ModelConfig(model="gpt-4o", api_key="sk-test"),
            fallback_model_cfg=None,
            reason="test",
        )
        mock_route = AsyncMock(return_value=routed)

        async with _converter_env(recent=["simple", "standard", "code"]):
            with patch("myrm_agent_harness.toolkits.llms.routing.complexity_router.route_task", mock_route):
                await _convert(turn)

        assert mock_route.call_args.kwargs["recent_tiers"] == [RoutingTier.SIMPLE, RoutingTier.STANDARD]

    async def test_short_followup_after_a_code_turn_stays_on_the_code_model(self) -> None:
        turn = _turn(query="继续", code_model_selection=_CODE, fallback_code_model_selection=_CODE_FALLBACK)

        async with _converter_env(recent=["code"]):
            params, tier, specialty, reason = await _convert(turn)

        assert params.model_cfg.model == "claude-3-7-sonnet-20250219"
        assert (tier, specialty) == ("code", "code")
        assert reason is not None
        assert "momentum_inherited(code)" in reason

    async def test_short_followup_without_code_history_is_not_routed_to_the_code_model(self) -> None:
        turn = _turn(query="继续", code_model_selection=_CODE, fallback_code_model_selection=_CODE_FALLBACK)

        async with _converter_env(recent=["standard"]):
            params, tier, specialty, _ = await _convert(turn)

        assert params.model_cfg.model == "gpt-4o"
        assert (tier, specialty) == (None, None)
