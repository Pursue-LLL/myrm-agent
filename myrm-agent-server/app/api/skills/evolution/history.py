from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.services.skills.evolution_reviews import EvolutionApplyError, rollback_evolution_review_record

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/{evolution_id}/rollback")
async def rollback_pending_evolution_record(evolution_id: str) -> dict[str, object]:
    try:
        return await rollback_evolution_review_record(evolution_id)
    except EvolutionApplyError as exc:
        if "not found" not in str(exc).lower():
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=404, detail=str(exc)) from exc
