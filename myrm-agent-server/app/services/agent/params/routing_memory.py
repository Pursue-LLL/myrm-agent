"""Per-chat routing memory for the Smart Routing block of the parameter converter.

[INPUT]
- app.database.repositories.chat_repo::ChatRepository.get_recent_routing_tiers / get_last_turn_routing_tier
  (POS: persisted `routingTier` history; the tier recorded by the latest user turn)
- app.services.agent.params.models::AgentRequest / ModelSelection (POS: request DTO and key-free model choice)
- myrm_agent_harness.toolkits.llms.routing::RoutingTier / TaskSpecialty (POS: complexity tiers and domain specialties)

[OUTPUT]
- RecentRouting / load_recent_routing(): recent routing history of a chat, split into the momentum inputs of the
  complexity router (tiers) and the specialty router (specialties)
- load_retry_baseline() / complaint_floor(): complexity tier of the answer turn a retry replaces, and the tier floor of
  that retry, climbing to the first rung that runs a different model config than the answer being retried
- remember_turn_routing() / resolve_turn_routing(): routing outcome of the latest user turn, reused when that turn
  is resumed after a human-in-the-loop interrupt

[POS]
Routing context that survives across requests of one chat. `routingTier` is persisted as either a complexity tier or a
specialty slot hit, so history parsing partitions it by enum. The tier recorded by the answer turn being retried is
the baseline a retry climbs from; rows the system appended to that turn (background-job notices, auto-continue) are not
answers and are skipped, and a turn that records no complexity tier (fast mode, pinned model, deep research without
escalation) ran the main model. Resume requests (tool approval, plan confirmation) carry
only the main model selection, so without this memory they would be re-routed and silently continue the interrupted
turn on a different model with a cold prompt cache. The memory is process-local, like the in-process HITL timeout
scheduler it complements; losing it (restart, LRU eviction) degrades to re-routing the resume request.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from myrm_agent_harness.toolkits.llms.routing import RoutingTier, TaskSpecialty

from app.core.types import ModelConfig

from .models import AgentRequest, ModelSelection

logger = logging.getLogger(__name__)

_MAX_REMEMBERED_CHATS = 256

SelectionResolver = Callable[[ModelSelection, dict[str, object] | None], Awaitable[ModelConfig]]


@dataclass(frozen=True, slots=True)
class RecentRouting:
    """Routing history of a chat, oldest first."""

    tiers: list[RoutingTier] = field(default_factory=list)
    specialties: list[TaskSpecialty] = field(default_factory=list)


_TIER_BY_VALUE = {tier.value: tier for tier in RoutingTier}
_SPECIALTY_BY_VALUE = {specialty.value: specialty for specialty in TaskSpecialty}


def split_recent_routing(values: Sequence[str]) -> RecentRouting:
    """Partition persisted `routingTier` values by the enum that recognises them.

    `reasoning` belongs to both enums; the turn was reasoning-class either way, so it feeds both histories.
    """
    return RecentRouting(
        tiers=[_TIER_BY_VALUE[value] for value in values if value in _TIER_BY_VALUE],
        specialties=[_SPECIALTY_BY_VALUE[value] for value in values if value in _SPECIALTY_BY_VALUE],
    )


async def load_recent_routing(chat_id: str | None) -> RecentRouting:
    """Load the momentum inputs of *chat_id*; empty when there is no chat or the lookup fails."""
    if not chat_id:
        return RecentRouting()
    try:
        from app.database.connection import get_session
        from app.database.repositories.chat_repo import ChatRepository

        async with get_session() as db:
            values = await ChatRepository.get_recent_routing_tiers(db, chat_id)
    except Exception as exc:
        logger.warning("Failed to load recent routing history, routing without momentum: %s", exc)
        return RecentRouting()
    return split_recent_routing(values)


async def load_retry_baseline(chat_id: str | None) -> RoutingTier | None:
    """Complexity tier recorded by the answer turn a retry replaces.

    None when that turn recorded no complexity tier (it ran the main model or a specialty slot) or when there is no
    chat or the lookup fails; `complaint_floor` then climbs from the standard rung.
    """
    if not chat_id:
        return None
    try:
        from app.database.connection import get_session
        from app.database.repositories.chat_repo import ChatRepository

        async with get_session() as db:
            value = await ChatRepository.get_last_turn_routing_tier(db, chat_id)
    except Exception as exc:
        logger.warning("Failed to load the retry baseline, climbing from the main model: %s", exc)
        return None
    return _TIER_BY_VALUE.get(value) if value is not None else None


_TIER_LADDER = (RoutingTier.SIMPLE, RoutingTier.STANDARD, RoutingTier.REASONING)


def _answer_config(cfg: ModelConfig) -> tuple[object, ...]:
    """Fields that change what a request returns; credentials, context budget and capability flags do not."""
    return (cfg.model, cfg.base_url, cfg.temperature, cfg.reasoning_effort, cfg.model_kwargs, cfg.wire_protocol)


def complaint_floor(
    last_tier: RoutingTier | None,
    *,
    standard: ModelConfig,
    light: ModelConfig | None,
    reasoning: ModelConfig | None,
) -> tuple[RoutingTier, bool]:
    """Lowest tier a retry may run on, and whether it moves to a different model config than the last answer.

    Auto-picked slots do not exclude the main model, so a rung can run the very config that just answered. The climb
    therefore skips such rungs instead of stepping one tier name at a time. When no rung above the last tier differs,
    the floor holds at the last tier (it never drops) and the caller must not report an upgrade. An answer that
    recorded no complexity tier (*last_tier* None) ran the main model, so the climb starts from the standard rung.
    """
    baseline = RoutingTier.STANDARD if last_tier is None else last_tier
    rungs = {
        RoutingTier.SIMPLE: standard if light is None else light,
        RoutingTier.STANDARD: standard,
        RoutingTier.REASONING: standard if reasoning is None else reasoning,
    }
    last_answer = _answer_config(rungs[baseline])
    for tier in _TIER_LADDER[_TIER_LADDER.index(baseline) + 1 :]:
        if _answer_config(rungs[tier]) != last_answer:
            return tier, True
    return baseline, False


@dataclass(frozen=True, slots=True)
class TurnRouting:
    """Routing outcome of a user turn, kept as key-free selections so credentials are re-resolved on resume."""

    main_identity: tuple[str, str] | None
    tier: str | None
    specialty: str | None
    reason: str | None
    model_selection: ModelSelection | None
    fallback_selection: ModelSelection | None


@dataclass(frozen=True, slots=True)
class ResolvedTurnRouting:
    """A remembered routing outcome resolved against the current provider configuration."""

    model_cfg: ModelConfig
    fallback_model_cfg: ModelConfig | None
    tier: str | None
    specialty: str | None
    reason: str | None


_turns: OrderedDict[str, TurnRouting] = OrderedDict()


def _main_identity(request: AgentRequest) -> tuple[str, str] | None:
    selection = request.model_selection
    return (selection.provider_id, selection.model) if selection else None


def _slot_selections(
    request: AgentRequest,
    tier: str | None,
    specialty: str | None,
) -> tuple[ModelSelection | None, ModelSelection | None]:
    """Request slots that supplied the routed model and its fallback; (None, None) when the main model ran."""
    if specialty == TaskSpecialty.CODE:
        return request.code_model_selection, request.fallback_code_model_selection
    if specialty == TaskSpecialty.LONG_DOC:
        return request.long_doc_model_selection, request.fallback_long_doc_model_selection
    if specialty == TaskSpecialty.REASONING:
        return request.reasoning_model_selection, None
    if specialty is None and tier == RoutingTier.SIMPLE:
        return request.light_model_selection, request.fallback_light_model_selection
    if specialty is None and tier == RoutingTier.REASONING:
        return request.reasoning_model_selection, request.fallback_reasoning_model_selection
    return None, None


def remember_turn_routing(
    request: AgentRequest,
    *,
    tier: str | None,
    specialty: str | None,
    reason: str | None,
) -> None:
    """Record the routing outcome of a user turn. Every user turn overwrites its chat's entry, routed or not."""
    chat_id = request.chat_id
    if not chat_id:
        return
    model_selection, fallback_selection = _slot_selections(request, tier, specialty)
    _turns[chat_id] = TurnRouting(
        main_identity=_main_identity(request),
        tier=tier,
        specialty=specialty,
        reason=reason,
        model_selection=model_selection,
        fallback_selection=fallback_selection,
    )
    _turns.move_to_end(chat_id)
    while len(_turns) > _MAX_REMEMBERED_CHATS:
        _turns.popitem(last=False)


async def resolve_turn_routing(
    request: AgentRequest,
    *,
    resolve: SelectionResolver,
    providers_dict: dict[str, object] | None,
    model_cfg: ModelConfig,
    fallback_model_cfg: ModelConfig | None,
) -> ResolvedTurnRouting | None:
    """Reuse the routing outcome of the interrupted turn for a resume request.

    *model_cfg* / *fallback_model_cfg* are the main-model configs of the resume request and are returned as-is when
    the interrupted turn ran on the main model. Returns None, so the caller routes normally, when nothing is
    remembered, the user switched the main model since, or a remembered slot model can no longer be resolved.
    """
    chat_id = request.chat_id
    turn = _turns.get(chat_id) if chat_id else None
    if turn is None or turn.main_identity != _main_identity(request):
        return None
    try:
        if turn.model_selection is not None:
            model_cfg = await resolve(turn.model_selection, providers_dict)
        if turn.fallback_selection is not None:
            fallback_model_cfg = await resolve(turn.fallback_selection, providers_dict)
    except ValueError:
        logger.warning("Remembered routing model is no longer available, re-routing resume: chat_id=%s", chat_id)
        return None
    return ResolvedTurnRouting(
        model_cfg=model_cfg,
        fallback_model_cfg=fallback_model_cfg,
        tier=turn.tier,
        specialty=turn.specialty,
        reason=turn.reason,
    )
