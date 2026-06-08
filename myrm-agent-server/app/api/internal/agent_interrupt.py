"""Control Plane → sandbox agent interrupt (no /api/v1 prefix).

[INPUT]
- Control Plane HTTP POST with interrupt signal

[OUTPUT]
- POST /api/agent/interrupt: Interrupt running agent execution

[POS]
CP-to-sandbox internal endpoint for interrupting agent execution.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.post("/agent/interrupt", tags=["agents"])
async def interrupt_agent() -> JSONResponse:
    from app.services.agent.gateway import get_agent_gateway

    gateway = get_agent_gateway()
    interrupted = gateway.interrupt()
    return JSONResponse({"interrupted": interrupted})
