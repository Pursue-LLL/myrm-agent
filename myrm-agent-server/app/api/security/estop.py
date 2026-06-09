"""Emergency Stop (E-Stop) HTTP API for WebUI.

[INPUT]
- POST /security/estop: Activate or resume the global tool-freeze.

[OUTPUT]
- JSON: { level, reason, activated_at, activated_by }

[POS]
WebUI-facing endpoint that bridges the frontend /freeze command to the
harness EStopGuard singleton. No CP token required (WebUI session auth).
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/security", tags=["security"])


class EStopRequest(BaseModel):
    action: Literal["activate", "resume"]
    level: Literal["tool_freeze", "kill_all"] = "tool_freeze"
    reason: str = Field(default="User triggered via WebUI")


class EStopResponse(BaseModel):
    level: str
    reason: str
    activated_at: float
    activated_by: str


@router.post("/estop", response_model=EStopResponse)
async def estop_action(body: EStopRequest) -> EStopResponse:
    """Activate or resume the global E-Stop guard."""
    from myrm_agent_harness.agent.security.guards.estop import (
        EStopLevel,
        get_estop_guard,
    )

    guard = get_estop_guard()

    if body.action == "activate":
        level = EStopLevel(body.level)
        state = guard.activate(level=level, reason=body.reason, activated_by="webui_user")
    elif body.action == "resume":
        state = guard.resume(resumed_by="webui_user")
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")

    return EStopResponse(
        level=state.level.value,
        reason=state.reason,
        activated_at=state.activated_at,
        activated_by=state.activated_by,
    )


@router.get("/estop", response_model=EStopResponse)
async def estop_status() -> EStopResponse:
    """Return current E-Stop state."""
    from myrm_agent_harness.agent.security.guards.estop import get_estop_guard

    guard = get_estop_guard()
    state = guard.state
    return EStopResponse(
        level=state.level.value,
        reason=state.reason,
        activated_at=state.activated_at,
        activated_by=state.activated_by,
    )
