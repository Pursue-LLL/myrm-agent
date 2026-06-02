import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from myrm_agent_harness.utils.runtime.cancellation import CancellationRegistry, CancelReason

from app.config.settings import settings
from app.core.infra.limiter import limiter
from app.services.agent.gateway import get_agent_gateway

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/agent/{message_id}/cancel")
@limiter.limit(settings.rate_limit.chat)
async def cancel_agent_request(
    message_id: str,
    http_request: Request,
) -> JSONResponse:
    """Cancel an active agent request by message ID.

    Allows users to manually stop agent execution without closing the browser tab.
    """

    from app.core.utils.response_utils import error_response, success_response

    success = CancellationRegistry.cancel(message_id, CancelReason.USER_CANCELLED)

    if success:
        logger.info(f"⛔ User cancelled agent request: message_id={message_id}")
        return success_response(data={"cancelled": True, "message_id": message_id})

    return error_response(message="Agent request not found or already completed", code=404)


@router.get("/active-sessions")
@limiter.limit("30/minute")
async def get_active_sessions(
    request: Request,
) -> JSONResponse:
    """Get active agent sessions for Multi-Pane status overview.

    Returns running sessions and available concurrent execution slots.
    """
    from app.core.utils.response_utils import success_response

    gateway = get_agent_gateway()
    return success_response(
        data={
            "activeSessions": gateway.get_active_sessions(),
            "maxConcurrent": gateway.config.max_per_user,
            "availableSlots": gateway.get_available_slots(),
        }
    )
