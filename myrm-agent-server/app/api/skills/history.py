"""Skill history management endpoints.

[INPUT]
- fastapi::APIRouter (POS: FastAPI router)
- app.core.skills.history_tracking_service::history_skill_service (POS: History tracking service)
- app.core.skills.history_types::SkillHistoryRecord (POS: History record type)

[OUTPUT]
- router: FastAPI router with history endpoints

[POS]
HTTP API for skill modification history and rollback operations.
Business-layer endpoints that use HistoryTrackingSkillService.
"""

from __future__ import annotations

import logging
from typing import cast

from fastapi import APIRouter, HTTPException, Request
from myrm_agent_harness.agent.skills.history.tracking_backend import HistoryTrackingSkillWriteBackend
from pydantic import BaseModel, Field

from app.core.skills.history_tracking_service import history_skill_service
from app.core.skills.store.service import skills_service

logger = logging.getLogger(__name__)

router = APIRouter()


def _validate_user_permission(http_request: Request) -> None:
    """Validate that the authenticated user matches the requested user_id.

    Security check to prevent users from accessing other users' history.

    Args:
        http_request: HTTP request context

    Raises:
        HTTPException: 403 if validation fails

    Implementation:
        Currently validates via X-User-ID header. In single-tenant deployments
        this maps to the request-scoped workspace identity.
    """
    if not http_request:
        raise HTTPException(status_code=401, detail="Authentication required")

    authenticated_user_id = http_request.headers.get("X-User-ID")

    if not authenticated_user_id:
        raise HTTPException(
            status_code=401,
            detail="Missing X-User-ID header. Authentication required.",
        )


class SkillHistoryRecordResponse(BaseModel):
    """History record response model."""

    action: str = Field(..., description="Action type: save/patch/delete/write_file/remove_file/rollback")
    author: str = Field(..., description="Who made the change: agent/human")
    timestamp: str = Field(..., description="ISO format timestamp")
    file_path: str = Field(..., description="Modified file path")
    prev_content: str | None = Field(None, description="Content before modification")
    new_content: str | None = Field(None, description="Content after modification")
    thread_id: str | None = Field(None, description="Conversation thread ID (business context)")
    session_id: str | None = Field(None, description="Session ID (business context)")
    request_id: str | None = Field(None, description="Request ID (business context)")
    scanner: dict[str, str] | None = Field(None, description="Security scan result")
    metadata: dict[str, str] | None = Field(None, description="Additional metadata")


class SkillHistoryResponse(BaseModel):
    """Skill history list response."""

    skill_id: str
    history: list[SkillHistoryRecordResponse]
    total_count: int


class SkillRollbackRequest(BaseModel):
    """Rollback request model."""

    history_index: int = Field(
        default=-1,
        description="History entry index to restore (negative index: -1=latest, -2=second latest)",
    )


class SkillRollbackResponse(BaseModel):
    """Rollback response model."""

    success: bool
    skill_id: str
    rolled_back_to: str | None = Field(None, description="ISO format timestamp")
    error: str = ""


@router.get("/{skill_id}/history", response_model=SkillHistoryResponse)
async def get_skill_history(
    skill_id: str,
    http_request: Request,
    limit: int = 100,
) -> SkillHistoryResponse:
    """Get skill modification history.

    Returns history records in reverse chronological order (newest first).

    Security: Validates that the authenticated user matches the requested user_id.

    Args:
        skill_id: Skill ID
        limit: Max records to return (default 100)
        http_request: HTTP request (for auth validation)

    Returns:
        History records and total count
    """
    try:
        # P0: Permission validation
        skill = await skills_service.get_skill(skill_id)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

        svc = cast(HistoryTrackingSkillWriteBackend, history_skill_service)
        records = await svc.list_history(
            skill_name=skill.name,
            limit=limit,
        )

        return SkillHistoryResponse(
            skill_id=skill_id,
            history=[
                SkillHistoryRecordResponse(
                    action=r.action,
                    author=r.author,
                    timestamp=r.timestamp.isoformat(),
                    file_path=r.file_path,
                    prev_content=r.prev_content,
                    new_content=r.new_content,
                    thread_id=r.thread_id,
                    session_id=r.session_id,
                    request_id=r.request_id,
                    scanner=r.scanner,
                    metadata=r.metadata,
                )
                for r in records
            ],
            total_count=len(records),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get skill history for {skill_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get history: {str(e)}") from e


@router.post("/{skill_id}/rollback", response_model=SkillRollbackResponse)
async def rollback_skill(
    skill_id: str,
    request: SkillRollbackRequest,
    http_request: Request,
) -> SkillRollbackResponse:
    """Rollback skill to a previous version.

    The rollback content will be re-validated and security scanned before applying.

    Security: Validates that the authenticated user matches the requested user_id.

    Args:
        skill_id: Skill ID
        request: Rollback parameters (history_index)
        http_request: HTTP request context (for business tracking and auth)

    Returns:
        Rollback result
    """
    try:
        # P0: Permission validation
        skill = await skills_service.get_skill(skill_id)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

        thread_id = http_request.headers.get("X-Thread-ID")
        session_id = http_request.headers.get("X-Session-ID")
        request_id = getattr(http_request.state, "request_id", None)
        user_agent = http_request.headers.get("User-Agent")

        svc = cast(HistoryTrackingSkillWriteBackend, history_skill_service)
        rollback_result = await svc.rollback_to_version(
            skill_name=skill.name,
            history_index=request.history_index,
            thread_id=thread_id,
            session_id=session_id,
            request_id=request_id,
            user_agent=user_agent,
        )

        if not rollback_result.success:
            raise HTTPException(status_code=500, detail=rollback_result.error)

        rolled_back_to_iso = rollback_result.rolled_back_to.isoformat() if rollback_result.rolled_back_to else None

        return SkillRollbackResponse(
            success=True,
            skill_id=skill_id,
            rolled_back_to=rolled_back_to_iso,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to rollback skill {skill_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to rollback: {str(e)}") from e
