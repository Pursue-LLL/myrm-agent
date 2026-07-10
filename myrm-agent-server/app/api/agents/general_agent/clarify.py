"""Deep Research phase response endpoints (clarification, plan confirmation).

[POS]
Handles user responses to orchestrator phase gates during Deep Research.
"""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic.alias_generators import to_camel

from app.services.agent.streaming import PhaseWaiter

logger = logging.getLogger(__name__)

router = APIRouter()


class ClarifyResponseRequest(BaseModel):
    message_id: str
    answer: str | list[str] | dict[str, str | list[str]]

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class PlanConfirmRequest(BaseModel):
    message_id: str
    action: str  # "confirm" | "edit" | "skip"
    modified_plan: str | None = None

    class Config:
        alias_generator = to_camel
        populate_by_name = True


@router.post("/clarify-response")
async def clarify_response(
    request: ClarifyResponseRequest,
) -> JSONResponse:
    """Resolve a pending Deep Research clarification question."""
    from app.core.utils.response_utils import error_response, success_response

    waiter = PhaseWaiter.get(request.message_id)
    if waiter is None:
        return error_response("No pending clarification for this message", code=404)

    waiter.resolve(request.answer)
    logger.info(
        "Clarification resolved: message_id=%s, len=%d",
        request.message_id,
        len(str(request.answer)),
    )
    return success_response(data={"status": "resolved"})


@router.post("/plan-confirm-response")
async def plan_confirm_response(
    request: PlanConfirmRequest,
) -> JSONResponse:
    """Resolve a pending Deep Research plan confirmation gate."""
    from app.core.utils.response_utils import error_response, success_response

    plan_key = f"plan:{request.message_id}"
    waiter = PhaseWaiter.get(plan_key)
    if waiter is None:
        return error_response("No pending plan confirmation for this message", code=404)

    if request.action == "edit" and request.modified_plan:
        waiter.resolve(request.modified_plan)
    else:
        waiter.resolve(None)

    logger.info(
        "Plan confirmation resolved: message_id=%s, action=%s",
        request.message_id,
        request.action,
    )
    return success_response(data={"status": "resolved", "action": request.action})
