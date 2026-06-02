"""
[INPUT]
- app.api.skills.evolution.helpers::_get_skill_store (POS: Helper functions for evolution API)
- myrm_agent_harness.agent.skills.evolution.infra.integration::EvolutionIntegration (POS: Integration helpers for skill evolution system)

[OUTPUT]
- fix_skill: Trigger a FIX evolution for an existing skill, optionally bypassing cooldown.

[POS]
Evolution API endpoint for triggering FIX evolution with GUI-First force retry support.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .helpers import _get_skill_store

router = APIRouter()


class FixSkillRequest(BaseModel):
    reason: str = ""
    force_retry: bool = False


@router.post("/fix/{skill_id}")
async def fix_skill(
    skill_id: str,
    request: FixSkillRequest,
) -> dict[str, str]:
    """Trigger a FIX evolution for an existing skill, optionally bypassing cooldown."""
    logger = logging.getLogger(__name__)

    store = _get_skill_store()
    try:
        skill = store.get_skill(skill_id)
    finally:
        store.close()
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    from myrm_agent_harness.agent.skills.evolution.infra.integration import (
        get_global_evolution_integration,
    )

    evolution = get_global_evolution_integration()
    if evolution is None or evolution.engine is None:
        raise HTTPException(
            status_code=503, detail="Evolution engine not initialized. Please try again later."
        )

    async def _run_fix() -> None:
        try:
            from myrm_agent_harness.agent.skills.evolution.core.types import (
                EvolutionRequest,
                EvolutionType,
            )

            evo_req = EvolutionRequest(
                evolution_type=EvolutionType.FIX,
                skill_id=skill_id,
                reason=request.reason,
                force_retry=request.force_retry,
            )

            if evolution.queue:
                from myrm_agent_harness.agent.skills.evolution.infra.queue import (
                    QueuePriority,
                )

                await evolution.queue.enqueue(evo_req, priority=QueuePriority.HIGH)
                logger.info("Enqueued FIX evolution for skill '%s'", skill_id)
            else:
                # Fallback if queue not enabled
                proposal = await evolution.engine.fix_skill(
                    skill_id=skill_id,
                    error_message=request.reason,
                )
                if proposal:
                    from app.services.agent.confidence_approval_flow import (
                        ConfidenceApprovalFlow,
                    )

                    flow = ConfidenceApprovalFlow()
                    await flow.process_evolution(proposal=proposal)
                    logger.info(
                        "FIX evolution for skill '%s' submitted for review", skill_id
                    )
        except Exception:
            logger.exception(
                "FIX evolution background task failed for skill '%s'", skill_id
            )

    asyncio.create_task(_run_fix())

    return {
        "status": "accepted",
        "message": f"FIX evolution for '{skill.name}' started.",
    }
