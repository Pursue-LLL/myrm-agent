"""Internal background shell status for control-plane deploy guards.

[INPUT]
- myrm_agent_harness.api.hooks::count_running_background_shell_jobs
- app.services.agent.shell_background_tasks::shell_registry_is_ephemeral (POS: REST-aligned durable flag)

[OUTPUT]
- GET /api/internal/background-shell/status: running job count + ephemeral flag

[POS]
CP-to-sandbox internal probe before container recreate / runtime rolling deploy.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.security.auth.control_plane_guard import verify_control_plane_token

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/internal/background-shell",
    tags=["internal-background-shell"],
    dependencies=[Depends(verify_control_plane_token)],
)


class BackgroundShellStatusResponse(BaseModel):
    running_count: int
    registry_ephemeral: bool = True


@router.get("/status", response_model=BackgroundShellStatusResponse)
async def background_shell_status() -> BackgroundShellStatusResponse:
    from myrm_agent_harness.api.hooks import count_running_background_shell_jobs

    from app.services.agent.shell_background_tasks import shell_registry_is_ephemeral

    count = count_running_background_shell_jobs()
    logger.debug("Background shell status probe: running_count=%s", count)
    return BackgroundShellStatusResponse(
        running_count=count,
        registry_ephemeral=shell_registry_is_ephemeral(),
    )
