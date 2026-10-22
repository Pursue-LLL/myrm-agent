"""FastAPI router for Multi-Agent Visual Timeline & Cherry-Pick Rollback (Item 61).

[INPUT]
- app.schemas.visual_timeline::{
    TimelineNodeRecordRequest, TimelineFilterCriteriaRequest,
  }
- app.services.agent.visual_timeline_service::{
    VisualTimelineService, get_visual_timeline_service,
  }

[OUTPUT]
- REST endpoints under /agents/visual-timeline for chronologic journal tracking,
  multi-dimensional filtering, and surgical cherry-pick rollback.

[POS]
- HTTP API layer for Item 61 non-destructive multi-agent collaboration rollback.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.schemas.visual_timeline import (
    TimelineFilterCriteriaRequest,
    TimelineNodeRecordRequest,
)
from app.services.agent.visual_timeline_service import (
    VisualTimelineService,
    get_visual_timeline_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/agents/visual-timeline",
    tags=["Multi-Agent Visual Timeline & Cherry-Pick Rollback"],
)


@router.post(
    "/nodes",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Record an atomic chronological action node onto the visual timeline",
)
async def record_timeline_node(
    req: TimelineNodeRecordRequest,
    service: VisualTimelineService = Depends(get_visual_timeline_service),
) -> StandardSuccessResponse:
    """Record an atomic action node produced by a human or subagent."""
    node_dto = service.record_node(req)
    return create_success_response(data=node_dto.model_dump())


@router.post(
    "/nodes/query",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Query timeline nodes matching multi-dimensional filters",
)
async def query_timeline_nodes(
    req: TimelineFilterCriteriaRequest,
    service: VisualTimelineService = Depends(get_visual_timeline_service),
) -> StandardSuccessResponse:
    """Query chronological action nodes filtered by session, actor, operation, tags, or time."""
    nodes = service.query_nodes(req)
    return create_success_response(data=[n.model_dump() for n in nodes])


@router.get(
    "/nodes/{node_id}",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Fetch a specific timeline node by its unique ID",
)
async def get_timeline_node(
    node_id: str,
    service: VisualTimelineService = Depends(get_visual_timeline_service),
) -> StandardSuccessResponse:
    """Retrieve details and diff patch for an individual timeline node."""
    node = service.get_node(node_id)
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Timeline node {node_id} not found",
        )
    return create_success_response(data=node.model_dump())


@router.post(
    "/nodes/{node_id}/rollback",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute a surgical cherry-pick rollback on a specific timeline node",
)
async def rollback_timeline_node(
    node_id: str,
    service: VisualTimelineService = Depends(get_visual_timeline_service),
) -> StandardSuccessResponse:
    """Perform surgical atomic rollback of a targeted node while preserving other changes."""
    result = service.rollback_node(node_id)
    return create_success_response(data=result.model_dump())
