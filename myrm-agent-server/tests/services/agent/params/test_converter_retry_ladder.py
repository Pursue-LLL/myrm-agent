"""Retry (complaint-up) through the real converter and router: every climb ends on a different model.

Auto-picked routing slots do not exclude the main model, so a user whose main model is the cheapest or the priciest
enabled model has a rung that runs the very model that just answered. The retry must skip such a rung, and a retry
that has nowhere stronger to go must not report an upgrade. Turns that are not retries keep their momentum.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

from app.core.types import ModelConfig
from app.services.agent.params.converter import convert_to_general_agent_params
from app.services.agent.params.models import AgentRequest, ModelSelection
from tests.api.agent.conftest import _build_mock_user_configs

_GREETING = "hi"
_HARD_FOLLOW_UPS = ("and for n=0?", "explain more", "so the answer is 15?")


async def _fake_resolve(selection: ModelSelection, providers: dict[str, object] | None) -> ModelConfig:
    return ModelConfig(
        model=selection.model,
        api_key="sk-test-retry-ladder",
        reasoning_effort=selection.reasoning_effort,
    )


@asynccontextmanager
async def _converter_env(history: list[str | None]) -> AsyncIterator[None]:
    """*history* is the chat's answers in order, None for an answer that recorded no tier; the last one is retried."""
    with (
        patch("app.services.agent.params.converter._resolve_model_config", new=_fake_resolve),
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new=AsyncMock(return_value=_build_mock_user_configs()),
        ),
        patch(
            "app.database.repositories.chat_repo.ChatRepository.get_recent_routing_tiers",
            new_callable=AsyncMock,
            return_value=[tier for tier in history if tier is not None],
        ),
        patch(
            "app.database.repositories.chat_repo.ChatRepository.get_last_turn_routing_tier",
            new_callable=AsyncMock,
            return_value=history[-1] if history else None,
        ),
    ):
        yield


def _selection(model: str, effort: str | None = None) -> dict[str, object]:
    selection: dict[str, object] = {"providerId": "openai", "model": model}
    if effort is not None:
        selection["reasoning_effort"] = effort
    return selection


def _turn(
    query: str,
    *,
    main: str,
    light: str,
    reasoning: str,
    reasoning_effort: str | None = None,
    retry: bool = False,
) -> AgentRequest:
    return AgentRequest(
        message_id="msg-retry-ladder",
        chat_id="chat-retry-ladder",
        query=query,
        action_mode="agent",
        model_selection=_selection(main),
        light_model_selection=_selection(light),
        reasoning_model_selection=_selection(reasoning, reasoning_effort),
        sibling_group_id="sibling-1" if retry else None,
    )


async def _convert(request: AgentRequest, history: list[str | None]):
    async with _converter_env(history):
        params, tier, _specialty, reason, _warnings, _archive = await convert_to_general_agent_params(request, [])
    return params, tier, reason


class TestRetrySkipsRungsThatRunTheSameModel:
    async def test_cheap_main_model_skips_the_light_rung_and_climbs_to_the_reasoning_model(self) -> None:
        turn = _turn(_GREETING, main="gpt-4o-mini", light="gpt-4o-mini", reasoning="gpt-4o", retry=True)

        params, tier, reason = await _convert(turn, ["simple"])

        assert params.model_cfg.model == "gpt-4o"
        assert tier == "reasoning"
        assert reason is not None and reason.startswith("min_tier_escalation(")

    async def test_premium_main_model_still_climbs_from_the_light_model_to_the_main_model(self) -> None:
        turn = _turn(_GREETING, main="gpt-4o", light="gpt-4o-mini", reasoning="gpt-4o", retry=True)

        params, tier, reason = await _convert(turn, ["simple"])

        assert params.model_cfg.model == "gpt-4o"
        assert tier == "standard"
        assert reason is not None and reason.startswith("min_tier_escalation(")

    async def test_distinct_rungs_climb_one_tier_per_retry(self) -> None:
        def retry() -> AgentRequest:
            return _turn(_GREETING, main="gpt-4o", light="gpt-4o-mini", reasoning="deepseek-reasoner", retry=True)

        after_light, _, _ = await _convert(retry(), ["simple"])
        after_standard, _, _ = await _convert(retry(), ["simple", "standard"])

        assert after_light.model_cfg.model == "gpt-4o"
        assert after_standard.model_cfg.model == "deepseek-reasoner"


class TestRetryWithoutAStrongerRung:
    async def test_holds_the_main_model_and_does_not_claim_an_upgrade(self) -> None:
        turn = _turn(_GREETING, main="gpt-4o", light="gpt-4o-mini", reasoning="gpt-4o", retry=True)

        params, tier, reason = await _convert(turn, ["simple", "standard"])

        assert params.model_cfg.model == "gpt-4o"
        assert tier == "standard"
        assert reason == "retry_floor_held"

    async def test_never_drops_below_the_previous_answer(self) -> None:
        turn = _turn(_GREETING, main="gpt-4o", light="gpt-4o-mini", reasoning="gpt-4o", retry=True)

        params, _, _ = await _convert(turn, ["standard"])

        assert params.model_cfg.model == "gpt-4o"

    async def test_top_rung_keeps_its_own_label(self) -> None:
        turn = _turn(_GREETING, main="gpt-4o", light="gpt-4o-mini", reasoning="deepseek-reasoner", retry=True)

        params, tier, reason = await _convert(turn, ["simple", "standard", "reasoning"])

        assert params.model_cfg.model == "deepseek-reasoner"
        assert tier == "reasoning"
        assert reason == "retry_floor_held"


class TestRetryOfAnAnswerWithoutAComplexityTier:
    """Fast mode, a pinned model and unescalated deep research record no tier: that answer ran the main model."""

    async def test_unrouted_answer_climbs_from_the_main_model_not_from_an_older_routed_turn(self) -> None:
        turn = _turn(_GREETING, main="gpt-4o", light="gpt-4o-mini", reasoning="deepseek-reasoner", retry=True)

        params, tier, reason = await _convert(turn, ["simple", None])

        assert params.model_cfg.model == "deepseek-reasoner"
        assert tier == "reasoning"
        assert reason is not None and reason.startswith("min_tier_escalation(")

    async def test_chat_without_any_routed_turn_climbs_from_the_main_model(self) -> None:
        turn = _turn(_GREETING, main="gpt-4o", light="gpt-4o-mini", reasoning="deepseek-reasoner", retry=True)

        params, tier, _ = await _convert(turn, [])

        assert params.model_cfg.model == "deepseek-reasoner"
        assert tier == "reasoning"

    async def test_unrouted_answer_with_no_stronger_model_holds_and_does_not_claim_an_upgrade(self) -> None:
        turn = _turn(_GREETING, main="gpt-4o", light="gpt-4o-mini", reasoning="gpt-4o", retry=True)

        params, tier, reason = await _convert(turn, ["simple", "simple", None])

        assert params.model_cfg.model == "gpt-4o"
        assert tier == "standard"
        assert reason == "retry_floor_held"


class TestSameModelWithADifferentConfigIsADistinctRung:
    async def test_higher_reasoning_effort_is_a_real_upgrade(self) -> None:
        turn = _turn(
            _GREETING,
            main="gpt-5",
            light="gpt-5-mini",
            reasoning="gpt-5",
            reasoning_effort="high",
            retry=True,
        )

        params, tier, reason = await _convert(turn, ["standard"])

        assert params.model_cfg.model == "gpt-5"
        assert params.model_cfg.reasoning_effort == "high"
        assert tier == "reasoning"
        assert reason is not None and reason.startswith("min_tier_escalation(")


class TestMomentumIsUntouched:
    async def test_follow_up_after_a_hard_turn_stays_on_the_main_model_when_the_reasoning_slot_is_the_main_model(
        self,
    ) -> None:
        for query in _HARD_FOLLOW_UPS:
            turn = _turn(query, main="gpt-4o", light="gpt-4o-mini", reasoning="gpt-4o")

            params, _, _ = await _convert(turn, ["reasoning"])

            assert params.model_cfg.model == "gpt-4o", query

    async def test_non_retry_turn_records_the_tier_the_router_returned(self) -> None:
        turn = _turn(_GREETING, main="gpt-4o", light="gpt-4o-mini", reasoning="gpt-4o")

        params, tier, _ = await _convert(turn, [])

        assert params.model_cfg.model == "gpt-4o-mini"
        assert tier == "simple"
