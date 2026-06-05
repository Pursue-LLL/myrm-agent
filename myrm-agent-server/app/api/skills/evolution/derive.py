"""
[INPUT]
- app.api.skills.evolution.helpers::_get_skill_store (POS: Helper functions for evolution API)
- myrm_agent_harness.agent.skills.evolution.infra.integration::EvolutionIntegration (POS: Integration helpers for skill evolution system)

[OUTPUT]
- derive_skill: Trigger a user-driven derived evolution for an existing skill.

[POS]
Evolution API endpoint for triggering derived evolution.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .helpers import _get_skill_store

router = APIRouter()


class DeriveSkillRequest(BaseModel):
    instruction: str


@router.post("/derive/{skill_id}")
async def derive_skill(
    skill_id: str,
    request: DeriveSkillRequest,
) -> dict[str, str]:
    """Trigger a user-driven derived evolution for an existing skill."""
    logger = logging.getLogger(__name__)

    store = _get_skill_store()
    try:
        skill = store.get_skill(skill_id)
    finally:
        store.close()
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    instruction = request.instruction.strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="Instruction must not be empty")

    from myrm_agent_harness.agent.skills.evolution.infra.integration import (
        get_global_evolution_integration,
    )

    evolution = get_global_evolution_integration()
    if evolution is None or evolution.engine is None:
        raise HTTPException(status_code=503, detail="Evolution engine not initialized. Please try again later.")

    async def _run_derive() -> None:
        try:
            from app.services.agent.confidence_approval_flow import (
                ConfidenceApprovalFlow,
            )

            proposal = await evolution.engine.derive_skill_simple(
                skill_id=skill_id,
                user_feedback=instruction,
            )
            if proposal is None:
                logger.warning("Derived evolution returned None for skill '%s'", skill_id)
                return

            flow = ConfidenceApprovalFlow()
            await flow.process_evolution(proposal=proposal)
            logger.info("Derived evolution for skill '%s' submitted for review", skill_id)
        except Exception:
            logger.exception("Derived evolution background task failed for skill '%s'", skill_id)

    asyncio.create_task(_run_derive())

    return {
        "status": "accepted",
        "message": f"Derived evolution for '{skill.name}' started. Check pending evolutions for review.",
    }
