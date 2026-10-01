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
from app.services.agent.steering import SteeringRegistry
from app.services.agent.stream_session import run_agent_stream

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/agent-stream", response_model=None)
@limiter.limit(settings.rate_limit.chat)
async def agent_stream(
    request: AgentRequest,
    http_request: Request,
) -> StreamingResponse | JSONResponse:
    from app.remote_access.mobile_gate import require_mobile_pair_chat_access

    require_mobile_pair_chat_access(http_request, request.chat_id)
    from app.services.loop.session_turn_arbiter import SessionTurnArbiter

    SessionTurnArbiter.get_instance().record_user_activity(request.chat_id)
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
    mode: str = "direct"
    quoted_ref: str | None = None
    in_reply_to_call_id: str | None = None
    question_context: str | None = None

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
    from app.remote_access.mobile_gate import require_mobile_pair_chat_access

    require_mobile_pair_chat_access(http_request, chat_id)
    if not body.message.strip():
        return error_response(message="Steering message cannot be empty", code=400)

    steer_payload = body.message.strip()
    if body.question_context and body.question_context.strip():
        steer_payload = f"[In reply to: {body.question_context.strip()}] {steer_payload}"

    if body.mode.strip().lower() == "policy":
        from app.services.agent.steering import policy_steer

        outcome = policy_steer(chat_id, steer_payload, quoted_ref=body.quoted_ref)
        if outcome["status"] == "no_active":
            return error_response(message="No active agent for this chat", code=404)
        if outcome["status"] == "too_large":
            return error_response(
                message="Steering message too large; reference artifacts instead",
                code=400,
            )
        logger.info(
            "User policy-steered agent: chat_id=%s status=%s",
            chat_id,
            outcome["status"],
        )
        return success_response(
            data={
                "steered": True,
                "chat_id": chat_id,
                "mode": "policy",
                "deduped": outcome["deduped"],
                "metrics": outcome["metrics"],
            }
        )

    success = SteeringRegistry.steer(chat_id, steer_payload)

    if success:
        if body.in_reply_to_call_id:
            from app.services.memory.consolidation_service import ConsolidationService

            ConsolidationService.record_steering_decision(
                session_id=chat_id,
                reply=body.message.strip(),
                question_context=body.question_context,
                call_id=body.in_reply_to_call_id,
            )
        logger.info("User steered agent: chat_id=%s", chat_id)
        return success_response(data={"steered": True, "chat_id": chat_id})

    return error_response(message="No active agent for this chat", code=404)


@router.get("/chats/{chat_id}/steer-metrics")
@limiter.limit(settings.rate_limit.chat)
async def steer_metrics(
    chat_id: str,
    http_request: Request,
) -> JSONResponse:
    from app.core.utils.response_utils import error_response, success_response
    from app.remote_access.mobile_gate import require_mobile_pair_chat_access
    from app.services.agent.steering import policy_metrics

    require_mobile_pair_chat_access(http_request, chat_id)
    if not SteeringRegistry.has_active(chat_id):
        return error_response(message="No active agent for this chat", code=404)
    return success_response(data={"chat_id": chat_id, "metrics": policy_metrics(chat_id)})


@router.post("/chats/{chat_id}/redirect")
@limiter.limit(settings.rate_limit.chat)
async def redirect_agent(
    chat_id: str,
    body: SteerRequest,
    http_request: Request,
) -> JSONResponse:
    from app.core.utils.response_utils import error_response, success_response
    from app.remote_access.mobile_gate import require_mobile_pair_chat_access

    require_mobile_pair_chat_access(http_request, chat_id)
    if not body.message.strip():
        return error_response(message="Redirect message cannot be empty", code=400)

    success = SteeringRegistry.redirect(chat_id, body.message)

    if success:
        logger.info("User redirected agent: chat_id=%s", chat_id)
        return success_response(data={"redirected": True, "chat_id": chat_id})

    return error_response(message="No active agent for this chat", code=404)


@router.post("/chats/{chat_id}/cancel")
@limiter.limit(settings.rate_limit.chat)
async def cancel_active_chat_agent(
    chat_id: str,
    http_request: Request,
) -> JSONResponse:
    from myrm_agent_harness.utils.runtime.cancellation import CancelReason

    from app.core.utils.response_utils import error_response, success_response
    from app.remote_access.mobile_gate import require_mobile_pair_chat_access
    from app.services.agent.gateway import get_agent_gateway

    require_mobile_pair_chat_access(http_request, chat_id)
    gateway = get_agent_gateway()
    message_id = gateway.get_active_message_id(chat_id)
    interrupted = gateway.interrupt_session(chat_id)
    registry_cancelled = False
    if message_id:
        registry_cancelled = CancellationRegistry.cancel(message_id, CancelReason.USER_CANCELLED)

    if not interrupted and not registry_cancelled:
        return error_response(message="No active agent for this chat", code=404)

    logger.info(
        "User cancelled active chat agent: chat_id=%s message_id=%s",
        chat_id,
        message_id,
    )
    return success_response(
        data={
            "cancelled": True,
            "chat_id": chat_id,
            "message_id": message_id,
        }
    )
