"""[INPUT]
- app.services.agent.params.models::AgentRequest (POS: Agent API request DTO)
- app.services.agent.params.model_plan::ModelPlan (POS: resolved model slots)
- app.services.agent.params.routing_memory (POS: cross-turn routing memory + HITL resume pinning)
- myrm_agent_harness.toolkits.llms.routing (POS: specialty + complexity routing engines)

[OUTPUT]
- RoutingOutcome: tier / specialty / reason attribution for the turn
- resolve_routing_outcome(): applies specialty, complexity and retry-floor routing to the model plan

[POS]
Routing stage of Agent request conversion. Decides which slot this turn runs on and reports the
attribution; it mutates ``ModelPlan.model_cfg`` / ``fallback_model_cfg`` in place.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from app.core.types import ModelConfig

from ..conversion.model_plan import ModelPlan, ModelResolver
from ..models import AgentRequest
from .routing_memory import (
    RecentRouting,
    complaint_floor,
    load_recent_routing,
    load_retry_baseline,
)
from .routing_memory import (
    resolve_turn_routing as resolve_pinned_turn_routing,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RoutingOutcome:
    """Attribution of the routing decision that produced this turn's model."""

    tier: str | None = None
    specialty: str | None = None
    reason: str | None = None


async def resolve_routing_outcome(
    request: AgentRequest,
    plan: ModelPlan,
    providers_dict: dict[str, object] | None,
    *,
    resolve: ModelResolver,
) -> RoutingOutcome:
    """Route the turn and overwrite ``plan.model_cfg`` / ``plan.fallback_model_cfg`` when a verdict wins."""

    model_cfg = plan.model_cfg
    fallback_model_cfg = plan.fallback_model_cfg
    routing_tier: str | None = None
    routing_specialty: str | None = None
    routing_reason: str | None = None

    # A resume continues the interrupted turn: reuse its routing outcome instead of re-routing an empty query.
    pinned_routing = (
        await resolve_pinned_turn_routing(
            request,
            resolve=resolve,
            providers_dict=providers_dict,
            model_cfg=model_cfg,
            fallback_model_cfg=fallback_model_cfg,
        )
        if request.resume_value is not None
        else None
    )
    if pinned_routing is not None:
        model_cfg = pinned_routing.model_cfg
        fallback_model_cfg = pinned_routing.fallback_model_cfg
        routing_tier = pinned_routing.tier
        routing_specialty = pinned_routing.specialty
        routing_reason = pinned_routing.reason

    recent_routing = RecentRouting()
    if pinned_routing is None and (
        request.code_model_selection
        or request.long_doc_model_selection
        or request.light_model_selection
        or request.reasoning_model_selection
    ):
        recent_routing = await load_recent_routing(request.chat_id)

    if pinned_routing is None and bool(request.code_model_selection or request.long_doc_model_selection):
        try:
            from myrm_agent_harness.toolkits.llms.routing import TaskSpecialty, route_task_specialty

            specialty_slots: dict[TaskSpecialty, ModelConfig] = {}
            specialty_fallback_slots: dict[TaskSpecialty, ModelConfig] = {}

            if request.code_model_selection:
                try:
                    specialty_slots[TaskSpecialty.CODE] = await resolve(request.code_model_selection, providers_dict)
                except ValueError:
                    logger.warning("Failed to resolve code specialty model")
            if request.fallback_code_model_selection:
                try:
                    specialty_fallback_slots[TaskSpecialty.CODE] = await resolve(
                        request.fallback_code_model_selection, providers_dict
                    )
                except ValueError:
                    pass

            if request.long_doc_model_selection:
                try:
                    specialty_slots[TaskSpecialty.LONG_DOC] = await resolve(request.long_doc_model_selection, providers_dict)
                except ValueError:
                    logger.warning("Failed to resolve long_doc specialty model")
            if request.fallback_long_doc_model_selection:
                try:
                    specialty_fallback_slots[TaskSpecialty.LONG_DOC] = await resolve(
                        request.fallback_long_doc_model_selection, providers_dict
                    )
                except ValueError:
                    pass

            if request.reasoning_model_selection and (request.code_model_selection or request.long_doc_model_selection):
                try:
                    reasoning_cfg_slot = await resolve(request.reasoning_model_selection, providers_dict)
                    specialty_slots[TaskSpecialty.REASONING] = reasoning_cfg_slot
                except ValueError:
                    pass

            specialty_result = await route_task_specialty(
                query=request.query,
                default_model_cfg=model_cfg,
                specialty_model_slots=specialty_slots if specialty_slots else None,
                specialty_fallback_slots=(specialty_fallback_slots if specialty_fallback_slots else None),
                default_fallback_cfg=fallback_model_cfg,
                recent_specialties=recent_routing.specialties or None,
            )

            if "specialty_slot_hit" in specialty_result.reason:
                model_cfg = specialty_result.model_cfg
                if specialty_result.fallback_model_cfg is not None:
                    fallback_model_cfg = specialty_result.fallback_model_cfg
                routing_tier = specialty_result.specialty.value
                routing_specialty = specialty_result.specialty.value
                routing_reason = specialty_result.reason
                logger.info(
                    "Specialty routing activated: specialty=%s model=%s reason=%s",
                    routing_specialty,
                    model_cfg.model,
                    specialty_result.reason,
                )
        except Exception:
            logger.warning("Specialty routing failed, using default model", exc_info=True)

    if pinned_routing is None and routing_tier is None and (request.light_model_selection or request.reasoning_model_selection):
        try:
            from myrm_agent_harness.toolkits.llms.routing.complexity_router import (
                route_task,
            )

            light_model_cfg = None
            if request.light_model_selection:
                try:
                    light_model_cfg = await resolve(request.light_model_selection, providers_dict)
                except ValueError:
                    logger.warning("Failed to resolve light model")

            light_fallback_cfg = None
            if request.fallback_light_model_selection:
                try:
                    light_fallback_cfg = await resolve(request.fallback_light_model_selection, providers_dict)
                except ValueError:
                    pass

            reasoning_model_cfg = None
            if request.reasoning_model_selection:
                try:
                    reasoning_model_cfg = await resolve(request.reasoning_model_selection, providers_dict)
                except ValueError:
                    logger.warning("Failed to resolve reasoning model")

            reasoning_fallback_cfg = None
            if request.fallback_reasoning_model_selection:
                try:
                    reasoning_fallback_cfg = await resolve(request.fallback_reasoning_model_selection, providers_dict)
                except ValueError:
                    pass

            judge_llm = None
            if plan.lite_model_cfg:
                from myrm_agent_harness.toolkits.llms import llm_manager

                try:
                    # judge 是确定性判定角色：低温保证分类稳定，与 harness 评估器
                    # （sufficiency/evaluator 默认 0.0）保持一致的「评审低温」语义。
                    # model_copy 不改动原 lite_model_cfg（frozen 实例），
                    # 该配置仅供 judge 使用，不影响 SIMPLE tier 的 light_model_cfg。
                    judge_llm = await llm_manager.get_llm_from_config(plan.lite_model_cfg.model_copy(update={"temperature": 0.0}))
                except Exception as exc:
                    logger.warning("Failed to create judge LLM for smart routing: %s", exc)

            from myrm_agent_harness.toolkits.llms.routing.complexity_router import (
                RoutingTier,
            )

            recent_routing_tiers = recent_routing.tiers or None

            complaint_min_tier: RoutingTier | None = None
            retry_climbs = True
            if request.sibling_group_id and not request.regenerate_instruction:
                complaint_min_tier, retry_climbs = complaint_floor(
                    await load_retry_baseline(request.chat_id),
                    standard=model_cfg,
                    light=light_model_cfg,
                    reasoning=reasoning_model_cfg,
                )

            route_started = time.perf_counter()
            routing_result = await route_task(
                query=request.query,
                standard_model_cfg=model_cfg,
                light_model_cfg=light_model_cfg,
                reasoning_model_cfg=reasoning_model_cfg,
                standard_fallback_cfg=fallback_model_cfg,
                light_fallback_cfg=light_fallback_cfg,
                reasoning_fallback_cfg=reasoning_fallback_cfg,
                judge_llm=judge_llm,
                recent_tiers=recent_routing_tiers,
                min_tier=complaint_min_tier,
            )
            routing_ms = (time.perf_counter() - route_started) * 1000
            model_cfg = routing_result.model_cfg
            if routing_result.fallback_model_cfg is not None:
                fallback_model_cfg = routing_result.fallback_model_cfg
            routing_tier = routing_result.tier.value
            routing_reason = routing_result.reason
            if not retry_climbs and routing_reason is not None and routing_reason.startswith("min_tier_escalation("):
                # The floor had no different model to move to, so the row must not claim an upgrade.
                routing_reason = "retry_floor_held"
            logger.info(
                "Smart routing: tier=%s model=%s reason=%s routing_ms=%.1f",
                routing_result.tier.value,
                model_cfg.model,
                routing_result.reason,
                routing_ms,
            )
        except Exception:
            logger.warning("Smart routing failed, using default model", exc_info=True)

    plan.model_cfg = model_cfg
    plan.fallback_model_cfg = fallback_model_cfg
    return RoutingOutcome(tier=routing_tier, specialty=routing_specialty, reason=routing_reason)
