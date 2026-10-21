"""Cron prerequisite check endpoint.

[INPUT]
- cron.schemas.PrerequisiteCheckRequest (POS: request schema)

[OUTPUT]
- POST /prerequisite-check — check manual execution verification stats before creating cron jobs

[POS]
Fixed-path sub-router for cron prerequisite preflight verification.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.cron.schemas import (
    PrerequisiteCheckRequest,
    PrerequisiteCheckResponse,
)

router = APIRouter()


@router.post("/prerequisite-check", response_model=PrerequisiteCheckResponse)
async def check_prerequisite(
    body: PrerequisiteCheckRequest,
) -> PrerequisiteCheckResponse:
    """Check manual success prerequisite stats for a workflow before creating cron."""
    from app.services.cron.prerequisite_service import CronPrerequisiteService

    stats = await CronPrerequisiteService.get_prerequisite_stats(
        prompt=body.prompt,
        agent_id=body.agent_id,
        workflow_template_id=body.workflow_template_id,
        command=body.command,
        tools_allowed=body.tools_allowed,
        chat_id=body.chat_id,
        threshold=body.threshold,
    )
    return PrerequisiteCheckResponse(
        fingerprint=stats.fingerprint,
        manual_success_count=stats.manual_success_count,
        threshold=stats.threshold,
        is_satisfied=stats.is_satisfied,
        chat_verified_count=stats.chat_verified_count,
        kanban_verified_count=stats.kanban_verified_count,
        override_allowed=stats.override_allowed,
    )
