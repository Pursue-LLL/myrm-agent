"""FastAPI router for Multi-Perspective Subagent Review & Bounded Review Loop (Item 32).

[INPUT]
- app.schemas.review_loop::{StartReviewLoopRequest, AdvanceReviewLoopRequest, ...}
- app.services.agent.review_loop_service::{ReviewLoopService, get_review_loop_service}

[OUTPUT]
- Router mounted under /chats/{chat_id}/review-loops.

[POS]
- HTTP endpoints for starting tri-perspective reviews, advancing remediation rounds,
  and monitoring convergence on clean diffs.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Path

from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.schemas.review_loop import (
    AdvanceReviewLoopRequest,
    StartReviewLoopRequest,
)
from app.services.agent.review_loop_service import (
    ReviewLoopService,
    get_review_loop_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats/{chat_id}/review-loops", tags=["Review Loops"])


@router.post(
    "/start",
    response_model=StandardSuccessResponse,
    summary="Start a multi-perspective parallel review loop",
)
def start_review_loop_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    req: StartReviewLoopRequest = ...,
    service: ReviewLoopService = Depends(get_review_loop_service),
) -> StandardSuccessResponse:
    """Trigger parallel review across Correctness, Test Coverage, and Simplicity perspectives."""
    if req.session_id != chat_id:
        # Align payload session_id to URL path parameter
        req = StartReviewLoopRequest(
            session_id=chat_id,
            diff_content=req.diff_content,
            context_description=req.context_description,
            max_rounds=req.max_rounds,
        )
    result = service.start_review_loop(req)
    return create_success_response(data=result)


@router.post(
    "/{loop_id}/advance",
    response_model=StandardSuccessResponse,
    summary="Advance to next round with remediated code diff",
)
def advance_review_loop_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    loop_id: str = Path(..., description="Review loop identifier"),
    req: AdvanceReviewLoopRequest = ...,
    service: ReviewLoopService = Depends(get_review_loop_service),
) -> StandardSuccessResponse:
    """Apply remediated code diff and trigger next concurrent review iteration."""
    result = service.advance_round(session_id=chat_id, loop_id=loop_id, req=req)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Review loop '{loop_id}' not found")
    return create_success_response(data=result)


@router.get(
    "/{loop_id}",
    response_model=StandardSuccessResponse,
    summary="Fetch status and rounds of a review loop",
)
def get_review_loop_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    loop_id: str = Path(..., description="Review loop identifier"),
    service: ReviewLoopService = Depends(get_review_loop_service),
) -> StandardSuccessResponse:
    """Retrieve round-by-round assessment history and convergence status."""
    result = service.get_review_loop(session_id=chat_id, loop_id=loop_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Review loop '{loop_id}' not found")
    return create_success_response(data=result)


@router.get(
    "",
    response_model=StandardSuccessResponse,
    summary="List review loops for a chat session",
)
def list_review_loops_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    service: ReviewLoopService = Depends(get_review_loop_service),
) -> StandardSuccessResponse:
    """List all review loops for the session."""
    result = service.list_review_loops(session_id=chat_id)
    return create_success_response(data=result)


@router.delete(
    "",
    response_model=StandardSuccessResponse,
    summary="Clear review loop history for a chat session",
)
def cleanup_review_loops_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    service: ReviewLoopService = Depends(get_review_loop_service),
) -> StandardSuccessResponse:
    """Clean up and release all review loop resources for the session."""
    cleaned = service.cleanup_session(session_id=chat_id)
    return create_success_response(data={"cleaned": cleaned, "session_id": chat_id})
