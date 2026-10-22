"""[INPUT] RegisterSubagentInstanceRequest, SubmitReportRequest, SubmitSettlementRequest, DrainQueueRequest, and chat_id path param.
[OUTPUT] StandardSuccessResponse containing registered instances, queue envelopes, drain responses, or queue status.
[POS] FastAPI router for Subagent report delivery wakeup and ordered settlement FIFO.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.schemas.report_fifo import (
    DrainQueueRequest,
    RegisterSubagentInstanceRequest,
    SubmitReportRequest,
    SubmitSettlementRequest,
)
from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.services.agent.report_fifo_service import (
    ReportFifoService,
    get_report_fifo_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats/{chat_id}/report-fifo", tags=["Subagent Report FIFO"])


@router.post(
    "/register",
    response_model=StandardSuccessResponse,
    summary="Register multi-named subagent instance configurations",
)
def register_instances_endpoint(
    chat_id: str,
    req: RegisterSubagentInstanceRequest,
    service: ReportFifoService = Depends(get_report_fifo_service),
) -> StandardSuccessResponse:
    """Register or update multi-named subagent instance configurations with dedicated permissions and report delivery."""
    registered = service.register_instances(chat_id=chat_id, instance_dtos=req.instances)
    return create_success_response(data=registered)


@router.post(
    "/report",
    response_model=StandardSuccessResponse,
    summary="Submit active subagent progress report",
)
def submit_report_endpoint(
    chat_id: str,
    req: SubmitReportRequest,
    service: ReportFifoService = Depends(get_report_fifo_service),
) -> StandardSuccessResponse:
    """Submit an active progress report; next-step delivery mode flags parent wakeup."""
    envelope = service.submit_report(chat_id=chat_id, req=req)
    return create_success_response(data=envelope)


@router.post(
    "/settlement",
    response_model=StandardSuccessResponse,
    summary="Submit automated settlement notice upon task termination",
)
def submit_settlement_endpoint(
    chat_id: str,
    req: SubmitSettlementRequest,
    service: ReportFifoService = Depends(get_report_fifo_service),
) -> StandardSuccessResponse:
    """Submit automated settlement notice guaranteed to drain strictly after preceding reports."""
    envelope = service.submit_settlement(chat_id=chat_id, req=req)
    return create_success_response(data=envelope)


@router.post(
    "/drain",
    response_model=StandardSuccessResponse,
    summary="Drain ordered events at parent step boundary",
)
def drain_queue_endpoint(
    chat_id: str,
    req: DrainQueueRequest,
    service: ReportFifoService = Depends(get_report_fifo_service),
) -> StandardSuccessResponse:
    """Drain events in strict FIFO Report-before-Settlement order at the parent agent step boundary."""
    outcome = service.drain_step_batch(chat_id=chat_id, max_items=req.max_items)
    return create_success_response(data=outcome)


@router.get(
    "/status",
    response_model=StandardSuccessResponse,
    summary="Get status overview of report FIFO queue",
)
def get_status_endpoint(
    chat_id: str,
    service: ReportFifoService = Depends(get_report_fifo_service),
) -> StandardSuccessResponse:
    """Fetch pending item count, registered instances count, and queued envelopes preview."""
    status = service.get_status(chat_id=chat_id)
    return create_success_response(data=status)


@router.delete(
    "",
    response_model=StandardSuccessResponse,
    summary="Release report FIFO resources for chat session",
)
def cleanup_report_fifo_endpoint(
    chat_id: str,
    service: ReportFifoService = Depends(get_report_fifo_service),
) -> StandardSuccessResponse:
    """Explicitly clean up coordinator and clear pending FIFO items upon session termination."""
    cleaned = service.cleanup_chat(chat_id=chat_id)
    return create_success_response(data={"chat_id": chat_id, "cleaned": cleaned})
