"""Per-chat routing memory: recent-history partitioning and the HITL resume pin."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from myrm_agent_harness.api import TaskSpecialty
from myrm_agent_harness.toolkits.llms.routing.complexity_router import RoutingTier

from app.core.types import ModelConfig
from app.services.agent.params import routing_memory
from app.services.agent.params.models import AgentRequest, ModelSelection
from app.services.agent.params.routing_memory import (
    complaint_floor,
    remember_turn_routing,
    resolve_turn_routing,
    split_recent_routing,
)

_MAIN = {"providerId": "openai", "model": "gpt-4o"}
_LIGHT = {"providerId": "openai", "model": "gpt-4o-mini"}
_LIGHT_FALLBACK = {"providerId": "openai", "model": "gpt-3.5"}
_REASONING = {"providerId": "deepseek", "model": "deepseek-reasoner"}
_REASONING_FALLBACK = {"providerId": "deepseek", "model": "deepseek-chat"}
_CODE = {"providerId": "anthropic", "model": "claude-sonnet"}
_CODE_FALLBACK = {"providerId": "deepseek", "model": "deepseek-coder"}
_LONG_DOC = {"providerId": "google", "model": "gemini-pro"}

_MAIN_CFG = ModelConfig(model="gpt-4o", api_key="sk-main")
_MAIN_FALLBACK_CFG = ModelConfig(model="gpt-4-turbo", api_key="sk-main-fallback")


def _request(chat_id: str | None = "chat-1", **overrides: object) -> AgentRequest:
    payload: dict[str, object] = {
        "message_id": "msg-1",
        "chat_id": chat_id,
        "query": "hello",
        "model_selection": _MAIN,
        "light_model_selection": _LIGHT,
        "fallback_light_model_selection": _LIGHT_FALLBACK,
        "reasoning_model_selection": _REASONING,
        "fallback_reasoning_model_selection": _REASONING_FALLBACK,
        "code_model_selection": _CODE,
        "fallback_code_model_selection": _CODE_FALLBACK,
        "long_doc_model_selection": _LONG_DOC,
    }
    payload.update(overrides)
    return AgentRequest(**payload)


def _resume_request(chat_id: str | None = "chat-1", **overrides: object) -> AgentRequest:
    """Resume bodies carry the main selection only — no routing slots."""
    payload: dict[str, object] = {
        "message_id": "msg-1",
        "chat_id": chat_id,
        "query": "",
        "model_selection": _MAIN,
        "resume_value": {"decision": "approve"},
    }
    payload.update(overrides)
    return AgentRequest(**payload)


class _Resolver:
    """Records resolved selections and can simulate an unavailable provider."""

    def __init__(self, unavailable: frozenset[str] = frozenset()) -> None:
        self.calls: list[str] = []
        self._unavailable = unavailable

    async def __call__(self, selection: ModelSelection, providers_dict: dict[str, object] | None) -> ModelConfig:
        self.calls.append(selection.model)
        if selection.model in self._unavailable:
            raise ValueError(f"No active API key for provider '{selection.provider_id}'")
        return ModelConfig(model=selection.model, api_key=f"sk-{selection.model}")


async def _resume(resolver: _Resolver, request: AgentRequest | None = None):
    return await resolve_turn_routing(
        request or _resume_request(),
        resolve=resolver,
        providers_dict=None,
        model_cfg=_MAIN_CFG,
        fallback_model_cfg=_MAIN_FALLBACK_CFG,
    )


@pytest.fixture(autouse=True)
def _isolated_memory() -> Iterator[None]:
    routing_memory._turns.clear()
    yield
    routing_memory._turns.clear()


class TestSplitRecentRouting:
    def test_partitions_tiers_and_specialties_and_drops_unknown_values(self) -> None:
        recent = split_recent_routing(["standard", "code", "reasoning", "long_doc", "bogus", "simple"])

        assert recent.tiers == [RoutingTier.STANDARD, RoutingTier.REASONING, RoutingTier.SIMPLE]
        assert recent.specialties == [TaskSpecialty.CODE, TaskSpecialty.REASONING, TaskSpecialty.LONG_DOC]

    def test_specialty_values_do_not_discard_the_tier_history(self) -> None:
        recent = split_recent_routing(["simple", "standard", "code"])

        assert recent.tiers == [RoutingTier.SIMPLE, RoutingTier.STANDARD]

    def test_empty_history(self) -> None:
        recent = split_recent_routing([])

        assert recent.tiers == []
        assert recent.specialties == []


class TestResolveTurnRouting:
    async def test_complexity_reasoning_turn_resumes_on_the_reasoning_slot(self) -> None:
        remember_turn_routing(_request(), tier="reasoning", specialty=None, reason="rule_based")
        resolver = _Resolver()

        resolved = await _resume(resolver)

        assert resolved is not None
        assert resolved.model_cfg.model == "deepseek-reasoner"
        assert resolved.fallback_model_cfg is not None
        assert resolved.fallback_model_cfg.model == "deepseek-chat"
        assert (resolved.tier, resolved.specialty, resolved.reason) == ("reasoning", None, "rule_based")

    async def test_simple_turn_resumes_on_the_light_slot(self) -> None:
        remember_turn_routing(_request(), tier="simple", specialty=None, reason="rule_based")

        resolved = await _resume(_Resolver())

        assert resolved is not None
        assert resolved.model_cfg.model == "gpt-4o-mini"
        assert resolved.fallback_model_cfg is not None
        assert resolved.fallback_model_cfg.model == "gpt-3.5"

    async def test_code_specialty_turn_resumes_on_the_code_slot(self) -> None:
        remember_turn_routing(_request(), tier="code", specialty="code", reason="specialty_slot_hit(code:x)")

        resolved = await _resume(_Resolver())

        assert resolved is not None
        assert resolved.model_cfg.model == "claude-sonnet"
        assert resolved.fallback_model_cfg is not None
        assert resolved.fallback_model_cfg.model == "deepseek-coder"
        assert (resolved.tier, resolved.specialty) == ("code", "code")

    async def test_long_doc_specialty_keeps_the_resume_fallback_when_no_slot_fallback_exists(self) -> None:
        remember_turn_routing(_request(), tier="long_doc", specialty="long_doc", reason="specialty_slot_hit(long_doc:x)")

        resolved = await _resume(_Resolver())

        assert resolved is not None
        assert resolved.model_cfg.model == "gemini-pro"
        assert resolved.fallback_model_cfg == _MAIN_FALLBACK_CFG

    async def test_reasoning_specialty_uses_the_reasoning_slot_without_a_slot_fallback(self) -> None:
        remember_turn_routing(_request(), tier="reasoning", specialty="reasoning", reason="specialty_slot_hit(reasoning:x)")

        resolved = await _resume(_Resolver())

        assert resolved is not None
        assert resolved.model_cfg.model == "deepseek-reasoner"
        assert resolved.fallback_model_cfg == _MAIN_FALLBACK_CFG

    async def test_main_model_turn_reuses_the_resume_configs_without_resolving_anything(self) -> None:
        remember_turn_routing(_request(), tier="standard", specialty=None, reason="default_standard")
        resolver = _Resolver()

        resolved = await _resume(resolver)

        assert resolved is not None
        assert resolved.model_cfg == _MAIN_CFG
        assert resolved.fallback_model_cfg == _MAIN_FALLBACK_CFG
        assert resolved.tier == "standard"
        assert resolver.calls == []

    async def test_unrouted_turn_pins_the_main_model(self) -> None:
        remember_turn_routing(_request(), tier=None, specialty=None, reason=None)

        resolved = await _resume(_Resolver())

        assert resolved is not None
        assert resolved.model_cfg == _MAIN_CFG
        assert resolved.tier is None

    async def test_later_user_turn_overwrites_the_remembered_slot(self) -> None:
        remember_turn_routing(_request(), tier="reasoning", specialty=None, reason="rule_based")
        remember_turn_routing(_request(), tier=None, specialty=None, reason=None)

        resolved = await _resume(_Resolver())

        assert resolved is not None
        assert resolved.model_cfg == _MAIN_CFG

    async def test_changed_main_model_selection_ignores_the_memory(self) -> None:
        remember_turn_routing(_request(), tier="reasoning", specialty=None, reason="rule_based")
        switched = _resume_request(model_selection={"providerId": "anthropic", "model": "claude-opus"})

        assert await _resume(_Resolver(), switched) is None

    async def test_missing_memory_or_chat_id_returns_none(self) -> None:
        assert await _resume(_Resolver()) is None
        assert await _resume(_Resolver(), _resume_request(chat_id=None)) is None

    async def test_unavailable_slot_model_returns_none_so_the_caller_reroutes(self) -> None:
        remember_turn_routing(_request(), tier="reasoning", specialty=None, reason="rule_based")

        assert await _resume(_Resolver(unavailable=frozenset({"deepseek-reasoner"}))) is None

    async def test_unavailable_slot_fallback_returns_none_so_the_caller_reroutes(self) -> None:
        remember_turn_routing(_request(), tier="reasoning", specialty=None, reason="rule_based")

        assert await _resume(_Resolver(unavailable=frozenset({"deepseek-chat"}))) is None

    async def test_memory_survives_repeated_resumes_of_the_same_turn(self) -> None:
        remember_turn_routing(_request(), tier="reasoning", specialty=None, reason="rule_based")

        first = await _resume(_Resolver())
        second = await _resume(_Resolver())

        assert first is not None
        assert second is not None
        assert first.model_cfg.model == second.model_cfg.model == "deepseek-reasoner"

    def test_remembering_without_chat_id_is_a_no_op(self) -> None:
        remember_turn_routing(_request(chat_id=None), tier="reasoning", specialty=None, reason="rule_based")

        assert len(routing_memory._turns) == 0

    def test_memory_is_bounded_and_evicts_the_least_recently_remembered_chat(self) -> None:
        limit = routing_memory._MAX_REMEMBERED_CHATS
        for index in range(limit + 1):
            remember_turn_routing(_request(chat_id=f"chat-{index}"), tier="simple", specialty=None, reason="rule_based")

        assert len(routing_memory._turns) == limit
        assert "chat-0" not in routing_memory._turns
        assert f"chat-{limit}" in routing_memory._turns


# Model slot a routed turn runs on, by harness enum member. None = the main model ran. A member added to the harness
# enums fails the coverage test below until it is classified here and in `routing_memory._slot_selections`.
_SPECIALTY_SLOT_MODEL: dict[TaskSpecialty, str | None] = {
    TaskSpecialty.CODE: "claude-sonnet",
    TaskSpecialty.LONG_DOC: "gemini-pro",
    TaskSpecialty.REASONING: "deepseek-reasoner",
    TaskSpecialty.MULTIMODAL: None,
    TaskSpecialty.CASUAL: None,
    TaskSpecialty.GENERAL: None,
}
_TIER_SLOT_MODEL: dict[RoutingTier, str | None] = {
    RoutingTier.SIMPLE: "gpt-4o-mini",
    RoutingTier.STANDARD: None,
    RoutingTier.REASONING: "deepseek-reasoner",
}


class TestSlotMapping:
    def test_every_harness_tier_and_specialty_is_classified(self) -> None:
        assert set(_SPECIALTY_SLOT_MODEL) == set(TaskSpecialty)
        assert set(_TIER_SLOT_MODEL) == set(RoutingTier)

    @pytest.mark.parametrize("specialty", list(TaskSpecialty))
    def test_specialty_turn_maps_to_its_slot(self, specialty: TaskSpecialty) -> None:
        selection, _ = routing_memory._slot_selections(_request(), specialty.value, specialty.value)

        assert (selection.model if selection else None) == _SPECIALTY_SLOT_MODEL[specialty]

    @pytest.mark.parametrize("tier", list(RoutingTier))
    def test_complexity_turn_maps_to_its_slot(self, tier: RoutingTier) -> None:
        selection, _ = routing_memory._slot_selections(_request(), tier.value, None)

        assert (selection.model if selection else None) == _TIER_SLOT_MODEL[tier]


def _cfg(model: str, **overrides: object) -> ModelConfig:
    return ModelConfig(model=model, api_key=f"sk-{model}", **overrides)


class TestComplaintFloor:
    """A retry climbs to the first rung that runs a different effective model config than the previous answer."""

    _MAIN = _cfg("gpt-4o")
    _LIGHT = _cfg("gpt-4o-mini")
    _REASONING = _cfg("deepseek-reasoner")

    def test_ladder_covers_every_harness_tier(self) -> None:
        assert set(routing_memory._TIER_LADDER) == set(RoutingTier)

    def test_distinct_rungs_climb_one_tier_per_retry(self) -> None:
        rungs = {"standard": self._MAIN, "light": self._LIGHT, "reasoning": self._REASONING}

        assert complaint_floor(RoutingTier.SIMPLE, **rungs) == (RoutingTier.STANDARD, True)
        assert complaint_floor(RoutingTier.STANDARD, **rungs) == (RoutingTier.REASONING, True)

    def test_top_rung_has_nothing_to_climb_to(self) -> None:
        floor = complaint_floor(RoutingTier.REASONING, standard=self._MAIN, light=self._LIGHT, reasoning=self._REASONING)

        assert floor == (RoutingTier.REASONING, False)

    def test_no_history_starts_at_the_standard_tier(self) -> None:
        floor = complaint_floor(None, standard=self._MAIN, light=self._LIGHT, reasoning=self._REASONING)

        assert floor == (RoutingTier.STANDARD, True)

    def test_unset_light_slot_is_skipped(self) -> None:
        floor = complaint_floor(RoutingTier.SIMPLE, standard=self._MAIN, light=None, reasoning=self._REASONING)

        assert floor == (RoutingTier.REASONING, True)

    def test_light_slot_equal_to_the_main_model_is_skipped(self) -> None:
        floor = complaint_floor(RoutingTier.SIMPLE, standard=self._MAIN, light=_cfg("gpt-4o"), reasoning=self._REASONING)

        assert floor == (RoutingTier.REASONING, True)

    def test_reasoning_slot_equal_to_the_main_model_holds_the_floor(self) -> None:
        floor = complaint_floor(RoutingTier.STANDARD, standard=self._MAIN, light=self._LIGHT, reasoning=_cfg("gpt-4o"))

        assert floor == (RoutingTier.STANDARD, False)

    def test_unset_reasoning_slot_holds_the_floor(self) -> None:
        floor = complaint_floor(RoutingTier.STANDARD, standard=self._MAIN, light=self._LIGHT, reasoning=None)

        assert floor == (RoutingTier.STANDARD, False)

    @pytest.mark.parametrize(
        "override",
        [{"reasoning_effort": "high"}, {"model_kwargs": {"thinking": {"budget_tokens": 8000}}}, {"temperature": 0.2}],
    )
    def test_same_model_with_a_different_answer_config_is_a_distinct_rung(self, override: dict[str, object]) -> None:
        floor = complaint_floor(
            RoutingTier.STANDARD, standard=self._MAIN, light=self._LIGHT, reasoning=_cfg("gpt-4o", **override)
        )

        assert floor == (RoutingTier.REASONING, True)

    def test_credentials_and_context_window_do_not_make_a_rung_distinct(self) -> None:
        main = _cfg("gpt-4o", max_context_tokens=8000)
        reasoning = ModelConfig(model="gpt-4o", api_key="sk-another-key", supports_vision=True)

        assert complaint_floor(RoutingTier.STANDARD, standard=main, light=self._LIGHT, reasoning=reasoning) == (
            RoutingTier.STANDARD,
            False,
        )
