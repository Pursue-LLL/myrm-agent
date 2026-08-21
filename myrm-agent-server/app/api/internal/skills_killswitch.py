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

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.security.auth.control_plane_guard import verify_control_plane_token

logger = logging.getLogger(__name__)


class KillSwitchBody(BaseModel):
    skill_id: str = Field(min_length=1)
    action: str = Field(pattern="^(disable|enable)$")


router = APIRouter(
    prefix="/api/internal/skills",
    tags=["internal-skills"],
    dependencies=[Depends(verify_control_plane_token)],
)


@router.post("/killswitch")
async def killswitch_action(body: KillSwitchBody) -> dict[str, str]:
    from app.core.skills.store.service import skills_service

    if body.action == "disable":
        await skills_service.user_config.disable_prebuilt_skill(body.skill_id)
        return {"status": "disabled", "skill_id": body.skill_id}
    await skills_service.user_config.enable_prebuilt_skill(body.skill_id)
    return {"status": "enabled", "skill_id": body.skill_id}
