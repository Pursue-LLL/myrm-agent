"""Frustration signal → Skill evolution routing callback.

Detects user frustration about style/format/workflow via regex,
identifies the most relevant editable skill, and triggers DERIVED
evolution to embed the preference permanently.

[INPUT]
- myrm_agent_harness.agent.skills.evolution.pipeline.frustration_detector (POS: Frustration signal detector)
- app.core.skills.store.service::skills_service (POS: Skill store service)
- app.services.skills.growth_lifecycle::process_skill_review_result (POS: Skill growth lifecycle)

[OUTPUT]
- make_frustration_skill_routing_callback: Session cleanup callback factory

[POS]
Frustration signal → Skill evolution routing callback.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.agent.skills.evolution.pipeline.frustration_detector import (
        FrustrationSignal,
    )

logger = logging.getLogger(__name__)

_COOLDOWN_SECONDS = 86400  # 24h per skill

_cooldown_registry: dict[str, float] = {}

_RELEVANCE_SYSTEM = (
    "You are a relevance judge. Given a user frustration signal and a skill name + description, "
    "determine if the frustration is directly relevant to this skill. "
    "Reply ONLY with 'YES' or 'NO'."
)

_RELEVANCE_PROMPT_TEMPLATE = (
    "User frustration: {frustration}\n\n"
    "Skill: {skill_name}\n"
    "Skill description: {skill_desc}\n\n"
    "Is this frustration directly relevant to how this skill instructs the agent to behave?"
)

_PREFERENCE_SUMMARY_SYSTEM = (
    "You are a preference extraction assistant. "
    "From the user's frustration message, extract their preference as a single "
    "imperative instruction (e.g. 'Never add comments unless explaining non-obvious logic'). "
    "Be concise and actionable. Output ONLY the instruction, nothing else."
)


def make_frustration_skill_routing_callback(
    agent_id: str,
    skill_ids: list[str],
    llm_func: Callable[[str, str], Awaitable[str]],
) -> Callable[[Sequence[dict[str, str]], str | None], Awaitable[None]]:
    """Create a session cleanup callback that routes frustration signals to skill evolution.

    Detects user frustration about style/format/workflow, identifies the most relevant
    editable skill, and triggers a DERIVED evolution to embed the preference permanently.
    Falls back gracefully when no matching skill is found.
    """

    async def _route(messages: Sequence[dict[str, str]], chat_id: str | None) -> None:
        try:
            await _run_frustration_routing(
                list(messages),
                agent_id=agent_id,
                skill_ids=skill_ids,
                llm_func=llm_func,
                chat_id=chat_id,
            )
        except Exception:
            logger.error("Frustration skill routing failed", exc_info=True)

    return _route


async def _run_frustration_routing(
    messages: list[dict[str, str]],
    *,
    agent_id: str,
    skill_ids: list[str],
    llm_func: Callable[[str, str], Awaitable[str]],
    chat_id: str | None,
) -> None:
    """Core logic: detect frustration → find relevant skill → trigger DERIVED evolution."""
    from myrm_agent_harness.agent.skills.evolution.pipeline.frustration_detector import (
        detect_frustration,
    )

    if len(messages) < 2:
        return

    signal = detect_frustration(messages)
    if signal is None:
        return

    if not skill_ids:
        logger.info(
            "Frustration detected (category=%s) but no skill_ids bound to agent %s",
            signal.category,
            agent_id,
        )
        return

    target_skill = await _find_relevant_skill(signal, skill_ids, llm_func)
    if target_skill is None:
        logger.info(
            "Frustration detected (category=%s) but no relevant editable skill found for agent %s",
            signal.category,
            agent_id,
        )
        return

    skill_id, skill_name = target_skill
    if not _check_cooldown(skill_id):
        logger.info(
            "Frustration routing cooldown active for skill %s, skipping",
            skill_name,
        )
        return

    preference = await _extract_preference_instruction(signal, llm_func)
    if not preference:
        return

    await _trigger_derived_evolution(
        skill_id=skill_id,
        skill_name=skill_name,
        preference=preference,
        signal=signal,
        agent_id=agent_id,
        chat_id=chat_id,
    )


def _check_cooldown(skill_id: str) -> bool:
    """Return True if the skill is NOT in cooldown (allowed to evolve)."""
    last_time = _cooldown_registry.get(skill_id)
    if last_time is None:
        return True
    return (time.monotonic() - last_time) >= _COOLDOWN_SECONDS


def _record_cooldown(skill_id: str) -> None:
    """Record that a frustration-driven evolution was triggered for this skill."""
    _cooldown_registry[skill_id] = time.monotonic()


async def _find_relevant_skill(
    signal: "FrustrationSignal",
    skill_ids: list[str],
    llm_func: Callable[[str, str], Awaitable[str]],
) -> tuple[str, str] | None:
    """Find the most relevant, editable skill for the frustration signal."""
    from myrm_agent_harness.utils.text_sanitizer import extract_and_strip_think_blocks

    from app.core.skills.store.service import skills_service

    for skill_id in skill_ids:
        skill = await skills_service.get_skill(skill_id)
        if skill is None:
            continue
        if skill.evolution_locked:
            continue

        prompt = _RELEVANCE_PROMPT_TEMPLATE.format(
            frustration=signal.user_message[:300],
            skill_name=skill.name,
            skill_desc=(skill.description or "")[:200],
        )
        raw = await llm_func(_RELEVANCE_SYSTEM, prompt)
        answer, _ = extract_and_strip_think_blocks(raw)
        if answer.strip().upper().startswith("YES"):
            return (skill_id, skill.name)

    return None


async def _extract_preference_instruction(
    signal: "FrustrationSignal",
    llm_func: Callable[[str, str], Awaitable[str]],
) -> str:
    """Extract a concise preference instruction from the frustration signal."""
    from myrm_agent_harness.utils.text_sanitizer import extract_and_strip_think_blocks

    raw = await llm_func(
        _PREFERENCE_SUMMARY_SYSTEM,
        f"User message: {signal.user_message[:500]}",
    )
    result, _ = extract_and_strip_think_blocks(raw)
    result = result.strip()
    if not result or result.upper() == "NONE":
        return ""
    return result[:500]


async def _trigger_derived_evolution(
    *,
    skill_id: str,
    skill_name: str,
    preference: str,
    signal: "FrustrationSignal",
    agent_id: str,
    chat_id: str | None,
) -> None:
    """Trigger DERIVED skill evolution with the preference feedback."""
    from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus
    from app.services.skills.growth_lifecycle import process_skill_review_result

    feedback = f"[PREFERENCE] {preference}"

    result: dict[str, object] = {
        "type": "skill_patch",
        "has_value": True,
        "skill_name": skill_name,
        "storage_skill_id": skill_id,
        "content": feedback,
        "description": f"User preference: {preference[:100]}",
        "source": "frustration_signal",
        "metadata": {
            "frustration_category": signal.category.value,
            "agent_id": agent_id,
            "chat_id": chat_id or "",
        },
    }

    await process_skill_review_result(result)
    _record_cooldown(skill_id)

    get_event_bus().publish(
        AppEvent(
            event_type=AppEventType.MEMORY_OPERATION,
            data={
                "operation": "frustration_skill_learned",
                "skill_id": skill_id,
                "skill_name": skill_name,
                "preference": preference[:200],
                "frustration_category": signal.category.value,
                "agent_id": agent_id,
                "chat_id": chat_id or "",
            },
        )
    )
