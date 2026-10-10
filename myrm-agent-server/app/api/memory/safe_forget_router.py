"""Safe episodic forget API router.

[INPUT]
- SafeForgetRequestDTO, SafeForgetResponseDTO, ParentProbeResponseDTO.
- SafeForgetService singleton dependency.

[OUTPUT]
- APIRouter exposing endpoints for memory probing, safe episodic forgetting, and audit inspection.

[POS]
- HTTP controller for Item 149 SafeEpisodicForgetSuite.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.safe_forget import (
    ParentProbeResponseDTO,
    SafeForgetRequestDTO,
    SafeForgetResponseDTO,
)
from app.services.memory.safe_forget_service import (
    SafeForgetService,
    get_safe_forget_service,
)

router = APIRouter(prefix="/episodic-forget", tags=["Memory: Safe Episodic Forget"])


@router.post(
    "/probe",
    response_model=ParentProbeResponseDTO,
    summary="Probe competing parent tiers and session authorization",
)
def probe_memory_parents(
    memory_id: str = Query(..., description="Target episodic memory ID"),
    caller_session_id: str = Query(..., description="Caller session ID"),
    allow_global: bool = Query(True, description="Whether global scope is accepted"),
    service: SafeForgetService = Depends(get_safe_forget_service),
) -> ParentProbeResponseDTO:
    """Probe whether an episodic memory exists, is authorized, and has competing parents."""
    return service.probe_parents(
        memory_id=memory_id,
        caller_session_id=caller_session_id,
        allow_global=allow_global,
    )


@router.post(
    "/execute",
    response_model=SafeForgetResponseDTO,
    summary="Safely forget an episodic memory with retention guards",
)
def execute_safe_forget(
    request: SafeForgetRequestDTO,
    service: SafeForgetService = Depends(get_safe_forget_service),
) -> SafeForgetResponseDTO:
    """Execute safe episodic forget with authorization check and shared child retention."""
    res = service.forget_episodic(request)
    if res.unauthorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized: caller session does not own memory and scope is not global.",
        )
    return res


@router.get(
    "/audit",
    summary="Retrieve recorded after-commit invalidation audit events",
)
def get_audit_events(
    service: SafeForgetService = Depends(get_safe_forget_service),
) -> list[dict[str, str | float]]:
    """Retrieve all after-commit invalidation events recorded in this session."""
    events = service.audit_events
    return [
        {
            "event_name": ev.event_name,
            "memory_id": ev.memory_id,
            "tier": ev.tier,
            "timestamp": ev.timestamp,
            "reason": ev.metadata.get("reason", ""),
            "session_id": ev.metadata.get("session_id", ""),
        }
        for ev in events
    ]
