"""[INPUT]
- TaskTimelineInspectorService: Service layer inspector singleton managing live timelines
- Pydantic models for request validation and structured OpenAPI schemas

[OUTPUT]
- router: APIRouter for /tasks/{task_id}/timeline and /tasks/{task_id}/interrupt

[POS]
HTTP routing layer for live task execution inspector and skill call timeline visualizer.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status
from pydantic import BaseModel, Field

from app.services.observability.timeline import TaskTimelineInspectorService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tasks-timeline"])


class TimelineIOMetricsSchema(BaseModel):
    input_chars: int = 0
    output_chars: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cache_hit: bool = False


class TimelineStepNodeSchema(BaseModel):
    node_id: str
    step_name: str
    parent_id: str | None = None
    step_index: int = 0
    node_type: str = "tool_invocation"
    status: str = "running"
    start_time_ms: float
    end_time_ms: float | None = None
    duration_ms: float | None = None
    input_payload: dict[str, str] | None = None
    output_payload: dict[str, str] | None = None
    metrics: TimelineIOMetricsSchema
    error_message: str | None = None
    children: list[TimelineStepNodeSchema] = Field(default_factory=list)


class TimelineSummarySchema(BaseModel):
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    running_steps: int = 0
    interrupted_steps: int = 0
    total_duration_ms: float = 0.0
    total_tokens: int = 0


class TaskTimelineResponse(BaseModel):
    task_id: str
    tree: list[TimelineStepNodeSchema]
    waterfall: list[TimelineStepNodeSchema]
    summary: TimelineSummarySchema
    interruptions: list[dict[str, str]] = Field(default_factory=list)


class TaskInterruptRequest(BaseModel):
    reason: Annotated[str, Field(default="user_barge_in", max_length=100, description="Interruption reason")]
    instruction: Annotated[str | None, Field(default=None, max_length=1000, description="Steering barge-in instruction")]


class TaskInterruptResponse(BaseModel):
    task_id: str
    interrupted_steps_count: int
    status: str
    instruction: str


@router.get(
    "/{task_id}/timeline",
    response_model=TaskTimelineResponse,
    summary="Get execution step tree and waterfall timeline for task",
)
async def get_task_timeline(
    task_id: Annotated[str, Path(description="Target task identifier")],
) -> TaskTimelineResponse:
    try:
        service = TaskTimelineInspectorService.get_instance()
        snapshot = service.get_timeline_snapshot(task_id)
        return TaskTimelineResponse.model_validate(snapshot)
    except Exception as exc:
        logger.exception(f"Failed to retrieve timeline for task {task_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve timeline: {exc}",
        ) from exc


@router.post(
    "/{task_id}/interrupt",
    response_model=TaskInterruptResponse,
    status_code=status.HTTP_200_OK,
    summary="Send mid-flight barge-in interrupt instruction to active task",
)
async def interrupt_task(
    task_id: Annotated[str, Path(description="Target task identifier")],
    payload: TaskInterruptRequest,
) -> TaskInterruptResponse:
    try:
        service = TaskTimelineInspectorService.get_instance()
        result = service.interrupt_task(
            task_id=task_id,
            reason=payload.reason,
            barge_in_instruction=payload.instruction,
        )
        return TaskInterruptResponse.model_validate(result)
    except Exception as exc:
        logger.exception(f"Failed to interrupt task {task_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to interrupt task: {exc}",
        ) from exc
