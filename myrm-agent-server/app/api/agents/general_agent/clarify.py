"""General Agent API — autonomous decision-making agent with streaming SSE."""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic.alias_generators import to_camel

from app.services.agent.streaming import (
    ClarificationWaiter,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class ClarifyResponseRequest(BaseModel):
    message_id: str
    answer: str | list[str] | dict[str, str | list[str]]

    class Config:
        alias_generator = to_camel
        populate_by_name = True


@router.post("/clarify-response")
async def clarify_response(
    request: ClarifyResponseRequest,
) -> JSONResponse:
    """Resolve a pending Deep Research clarification question."""
    from app.core.utils.response_utils import error_response, success_response

    waiter = ClarificationWaiter.get(request.message_id)
    if waiter is None:
        return error_response("No pending clarification for this message", code=404)

    waiter.resolve(request.answer)
    logger.info(
        "Clarification resolved: message_id=%s, len=%d",
        request.message_id,
        len(str(request.answer)),
    )
    return success_response(data={"status": "resolved"})
