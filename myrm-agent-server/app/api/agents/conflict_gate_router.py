"""
[INPUT]
- app.schemas.conflict_gate.*
- app.services.agent.conflict_gate_service.ConflictGateService
- fastapi (APIRouter, Depends, Path)

[OUTPUT]
- router (Conflict Gate API Router)
- POST /chats/{chat_id}/conflicts/evaluate
- GET /chats/{chat_id}/conflicts
- POST /chats/{chat_id}/conflicts/{conflict_id}/resolve

[POS]
Server 业务层多 Bot 并行产出冲突对账与合并前拦截门 REST 路由（Topic 12 · 第 19 项）。
提供写集冲突评估、待对账列表获取与对账解决 API 端点。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from fastapi.responses import JSONResponse

from app.core.utils.response_utils import error_response, success_response
from app.schemas.conflict_gate import (
    ConflictEvaluateRequestDTO,
    ConflictGateVerdictResponseDTO,
    ConflictResolveRequestDTO,
    ConflictResolveResponseDTO,
    WorkConflictItemDTO,
)
from app.services.agent.conflict_gate_service import ConflictGateService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats/{chat_id}/conflicts", tags=["Parallel Work Conflict Gate"])

_conflict_gate_service_instance: ConflictGateService | None = None


def get_conflict_gate_service() -> ConflictGateService:
    """Dependency injector for ConflictGateService."""
    global _conflict_gate_service_instance
    if _conflict_gate_service_instance is None:
        _conflict_gate_service_instance = ConflictGateService()
    return _conflict_gate_service_instance


@router.post("/evaluate", response_model=ConflictGateVerdictResponseDTO)
async def evaluate_parallel_work_conflicts(
    chat_id: Annotated[str, Path(..., description="The parent chat session ID")],
    req: ConflictEvaluateRequestDTO,
    service: Annotated[ConflictGateService, Depends(get_conflict_gate_service)],
) -> JSONResponse:
    """Evaluate candidate write fingerprints from parallel workers and return collision gate verdict."""
    try:
        verdict = service.evaluate_fingerprints(chat_id, req.fingerprints)
        return success_response(data=verdict.model_dump())
    except Exception as exc:
        logger.exception("Failed to evaluate work conflicts for %s", chat_id)
        return error_response(
            message=f"Failed to evaluate conflicts: {exc}",
            status_code=500,
        )


@router.get("", response_model=list[WorkConflictItemDTO])
async def get_session_pending_conflicts(
    chat_id: Annotated[str, Path(..., description="The parent chat session ID")],
    service: Annotated[ConflictGateService, Depends(get_conflict_gate_service)],
) -> JSONResponse:
    """Fetch all unresolved collision conflicts pending user reconciliation in this session."""
    try:
        conflicts = service.get_pending_conflicts(chat_id)
        return success_response(data=[c.model_dump() for c in conflicts])
    except Exception as exc:
        logger.exception("Failed to fetch pending conflicts for %s", chat_id)
        return error_response(
            message=f"Failed to fetch pending conflicts: {exc}",
            status_code=500,
        )


@router.post("/{conflict_id}/resolve", response_model=ConflictResolveResponseDTO)
async def resolve_work_conflict(
    chat_id: Annotated[str, Path(..., description="The parent chat session ID")],
    conflict_id: Annotated[str, Path(..., description="The target conflict item ID")],
    req: ConflictResolveRequestDTO,
    service: Annotated[ConflictGateService, Depends(get_conflict_gate_service)],
) -> JSONResponse:
    """Reconcile a pending collision conflict using a selected resolution strategy."""
    try:
        res = service.resolve_conflict(
            conflict_id=conflict_id,
            strategy=req.strategy,
            resolved_content=req.resolved_content,
        )
        if not res.success:
            return error_response(
                message=res.message,
                status_code=404,
            )
        return success_response(data=res.model_dump())
    except Exception as exc:
        logger.exception("Failed to resolve conflict %s", conflict_id)
        return error_response(
            message=f"Failed to resolve conflict: {exc}",
            status_code=500,
        )
