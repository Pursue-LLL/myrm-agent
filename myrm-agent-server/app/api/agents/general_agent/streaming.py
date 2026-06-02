"""General Agent API — HTTP/SSE transport for streaming agent execution."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from myrm_agent_harness.utils.runtime.cancellation import CancellationRegistry
from pydantic import BaseModel
from pydantic.alias_generators import to_camel

from app.config.settings import settings
from app.core.infra.limiter import limiter
from app.services.agent.params import AgentRequest
from app.services.agent.steering_registry import SteeringRegistry
from app.services.agent.stream_session.orchestrator import run_agent_stream

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/agent-stream", response_model=None)
@limiter.limit(settings.rate_limit.chat)
async def agent_stream(
    request: AgentRequest,
    http_request: Request,
) -> StreamingResponse | JSONResponse:
    return await run_agent_stream(request, http_request)


class TestMediaConfigRequest(BaseModel):
    """Request to test media generation configuration connectivity."""

    media_type: str
    provider: str = "openai"
    model: str = ""

    class Config:
        alias_generator = to_camel
        populate_by_name = True


@router.post("/agent/{message_id}/cancel")
@limiter.limit(settings.rate_limit.chat)
async def cancel_agent_request(
    message_id: str,
    http_request: Request,
) -> JSONResponse:
    from myrm_agent_harness.utils.runtime.cancellation import CancelReason

    from app.core.utils.response_utils import error_response, success_response

    success = CancellationRegistry.cancel(message_id, CancelReason.USER_CANCELLED)

    if success:
        logger.info("User cancelled agent request: message_id=%s", message_id)
        return success_response(data={"cancelled": True, "message_id": message_id})

    return error_response(message="Agent request not found or already completed", code=404)


class SteerRequest(BaseModel):
    message: str

    class Config:
        alias_generator = to_camel
        populate_by_name = True


@router.post("/chats/{chat_id}/steer")
@limiter.limit(settings.rate_limit.chat)
async def steer_agent(
    chat_id: str,
    body: SteerRequest,
    http_request: Request,
) -> JSONResponse:
    from app.core.utils.response_utils import error_response, success_response

    if not body.message.strip():
        return error_response(message="Steering message cannot be empty", code=400)

    success = SteeringRegistry.steer(chat_id, body.message)

    if success:
        logger.info("User steered agent: chat_id=%s", chat_id)
        return success_response(data={"steered": True, "chat_id": chat_id})

    return error_response(message="No active agent for this chat", code=404)
