"""Internal KillSwitch endpoint — invoked by Control Plane.

[INPUT]
- Control Plane HTTP POST with X-Telemetry-Token auth header

[OUTPUT]
- POST /api/internal/skills/killswitch: Enable/disable preset skills remotely

[POS]
CP-to-sandbox internal endpoint for remote skill killswitch management.
"""

from __future__ import annotations

import logging
import os
import secrets

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_TELEMETRY_TOKEN_ENV = "CONTROL_PLANE_TELEMETRY_TOKEN"
_TELEMETRY_TOKEN_HEADER = "X-Telemetry-Token"


class KillSwitchBody(BaseModel):
    skill_id: str = Field(min_length=1)
    action: str = Field(pattern="^(disable|enable)$")


router = APIRouter(prefix="/api/internal/skills", tags=["internal-skills"])


def _verify_token(request: Request) -> None:
    expected = os.getenv(_TELEMETRY_TOKEN_ENV, "").strip()
    provided = request.headers.get(_TELEMETRY_TOKEN_HEADER, "").strip()
    if not expected or not provided or not secrets.compare_digest(expected, provided):
        raise HTTPException(status_code=403, detail="Invalid telemetry token")


@router.post("/killswitch")
async def killswitch_action(body: KillSwitchBody, request: Request) -> dict[str, str]:
    _verify_token(request)
    from app.core.skills.store.service import skills_service

    if body.action == "disable":
        await skills_service.user_config.disable_prebuilt_skill(body.skill_id)
        return {"status": "disabled", "skill_id": body.skill_id}
    await skills_service.user_config.enable_prebuilt_skill(body.skill_id)
    return {"status": "enabled", "skill_id": body.skill_id}
