"""Smart Routing in deep research: only a reasoning verdict changes the planner/report model.

The report is the deliverable of a research run and research topics are short by nature (``Compare React vs Vue 2025``
scores SIMPLE on rules alone), so a SIMPLE verdict must not hand the main model over to the light slot. Routing did not
select the model of such a run, so no tier is recorded: a retry then climbs from the main model, and the standard
tier's per-token price that savings estimates are priced from is not diluted by the light-model research sub-agents.
Upgrades to the reasoning tier still apply, and the same query in every other mode keeps routing normally.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

from app.core.types import ModelConfig
from app.services.agent.params.converter import convert_to_general_agent_params
from app.services.agent.params.models import AgentRequest, ModelSelection

_MAIN = {"providerId": "openai", "model": "gpt-4o"}
_MAIN_FALLBACK = {"providerId": "openai", "model": "gpt-4o-fallback"}
_LIGHT = {"providerId": "openai", "model": "gpt-4o-mini"}
_LIGHT_FALLBACK = {"providerId": "openai", "model": "gpt-4o-mini-fallback"}
_REASONING = {"providerId": "deepseek", "model": "deepseek-reasoner"}
_SHORT_TOPIC = "Compare React vs Vue 2025"
_STANDARD_QUERY = "Explain how database indexes work and when they hurt write performance"
_MATH_QUERY = r"Please prove the following theorem step by step: \sum_{k=1}^n k = \frac{n(n+1)}{2}"


async def _fake_resolve(selection: ModelSelection, providers: dict[str, object] | None) -> ModelConfig:
    return ModelConfig(model=selection.model, api_key="sk-test-deep-research-routing")


@asynccontextmanager
async def _converter_env(history: list[str | None] | None = None) -> AsyncIterator[None]:
    with (
        patch("app.services.agent.params.converter._resolve_model_config", new=_fake_resolve),
        patch(
            "app.database.repositories.chat_repo.ChatRepository.get_recent_routing_tiers",
            new_callable=AsyncMock,
            return_value=history or [],
        ),
    ):
        yield


def _turn(query: str, action_mode: str, sibling_group_id: str | None = None) -> AgentRequest:
    return AgentRequest(
        message_id="msg-deep-research",
        chat_id="chat-deep-research",
        query=query,
        action_mode=action_mode,
        model_selection=_MAIN,
        fallback_model_selection=_MAIN_FALLBACK,
        light_model_selection=_LIGHT,
        fallback_light_model_selection=_LIGHT_FALLBACK,
        reasoning_model_selection=_REASONING,
        sibling_group_id=sibling_group_id,
    )


async def _convert(request: AgentRequest):
    params, tier, _specialty, reason, _warnings, _archive = await convert_to_general_agent_params(request, [])
    return params, tier, reason


class TestDeepResearchOnlyTakesAReasoningVerdict:
    async def test_short_topic_keeps_the_default_model_and_records_no_tier(self) -> None:
        async with _converter_env():
            params, tier, reason = await _convert(_turn(_SHORT_TOPIC, "deep_research"))

        assert params.model_cfg.model == "gpt-4o"
        assert params.fallback_model_cfg is not None
        assert params.fallback_model_cfg.model == "gpt-4o-fallback"
        assert (tier, reason) == (None, None)

    async def test_standard_verdict_keeps_the_default_model_and_records_no_tier(self) -> None:
        async with _converter_env():
            params, tier, reason = await _convert(_turn(_STANDARD_QUERY, "deep_research"))

        assert params.model_cfg.model == "gpt-4o"
        assert (tier, reason) == (None, None)

    async def test_same_standard_query_in_agent_mode_records_its_tier(self) -> None:
        async with _converter_env():
            _, tier, _ = await _convert(_turn(_STANDARD_QUERY, "agent"))

        assert tier == "standard"

    async def test_same_query_in_agent_mode_still_routes_to_the_light_model(self) -> None:
        async with _converter_env():
            params, tier, _ = await _convert(_turn(_SHORT_TOPIC, "agent"))

        assert params.model_cfg.model == "gpt-4o-mini"
        assert params.fallback_model_cfg is not None
        assert params.fallback_model_cfg.model == "gpt-4o-mini-fallback"
        assert tier == "simple"

    async def test_reasoning_verdict_still_upgrades_the_planner_model(self) -> None:
        async with _converter_env():
            params, tier, _ = await _convert(_turn(_MATH_QUERY, "deep_research"))

        assert params.model_cfg.model == "deepseek-reasoner"
        assert tier == "reasoning"

    async def test_retry_of_an_unrecorded_run_climbs_from_the_main_model_to_the_reasoning_model(self) -> None:
        async with _converter_env():
            _, first_tier, _ = await _convert(_turn(_SHORT_TOPIC, "deep_research"))
        assert first_tier is None

        async with _converter_env([first_tier]):
            params, tier, reason = await _convert(_turn(_SHORT_TOPIC, "deep_research", sibling_group_id="sibling-1"))

        assert params.model_cfg.model == "deepseek-reasoner"
        assert tier == "reasoning"
        assert reason is not None and reason.startswith("min_tier_escalation(")
