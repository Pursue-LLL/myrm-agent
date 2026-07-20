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
import os
import secrets

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_TELEMETRY_TOKEN_ENV = "CONTROL_PLANE_TELEMETRY_TOKEN"
_TELEMETRY_TOKEN_HEADER = "X-Telemetry-Token"

router = APIRouter(prefix="/api/internal/background-shell", tags=["internal-background-shell"])


class BackgroundShellStatusResponse(BaseModel):
    running_count: int
    registry_ephemeral: bool = True


def _verify_token(request: Request) -> None:
    expected = os.getenv(_TELEMETRY_TOKEN_ENV, "").strip()
    provided = request.headers.get(_TELEMETRY_TOKEN_HEADER, "").strip()
    if not expected or not provided or not secrets.compare_digest(expected, provided):
        raise HTTPException(status_code=403, detail="Invalid telemetry token")


@router.get("/status", response_model=BackgroundShellStatusResponse)
async def background_shell_status(request: Request) -> BackgroundShellStatusResponse:
    _verify_token(request)
    from myrm_agent_harness.api.hooks import count_running_background_shell_jobs

    from app.services.agent.shell_background_tasks import shell_registry_is_ephemeral

    count = count_running_background_shell_jobs()
    logger.debug("Background shell status probe: running_count=%s", count)
    return BackgroundShellStatusResponse(
        running_count=count,
        registry_ephemeral=shell_registry_is_ephemeral(),
    )
