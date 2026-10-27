"""REST API router for Persistent Kanban Job Queue and Massive Parallel Dogfooding Runner."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.kanban_queue import (
    AddCommentRequest,
    BatchRunnerStatusDTO,
    BlackboardEntryDTO,
    BlockKanbanJobRequest,
    ClaimKanbanJobRequest,
    CompleteKanbanJobRequest,
    CreateKanbanJobRequest,
    DecomposeJobRequest,
    DispatchWaveRequest,
    DispatchWaveResponseDTO,
    KanbanCommentDTO,
    KanbanJobDTO,
    KanbanJobStatusEnum,
    LinkDependencyRequest,
    SpecifyPromptRequest,
    SpecifyPromptResponse,
    SwarmTopologyStageEnum,
    ToggleCircuitBreakerRequest,
)
from app.services.agent.kanban_queue_service import (
    PersistentKanbanQueueService,
    get_kanban_queue_service,
)

router = APIRouter(prefix="/chats/{chat_id}/kanban-queue", tags=["Persistent Kanban Queue"])


@router.post("/jobs", response_model=KanbanJobDTO, status_code=status.HTTP_201_CREATED)
async def create_job(
    chat_id: str,
    req: CreateKanbanJobRequest,
    service: PersistentKanbanQueueService = Depends(get_kanban_queue_service),
) -> KanbanJobDTO:
    """Create a new persistent kanban job."""
    return service.create_job(chat_id, req)


@router.get("/jobs", response_model=List[KanbanJobDTO])
async def list_jobs(
    chat_id: str,
    status_filter: Optional[KanbanJobStatusEnum] = Query(None, alias="status"),
    stage_filter: Optional[SwarmTopologyStageEnum] = Query(None, alias="stage"),
    assignee: Optional[str] = Query(None),
    service: PersistentKanbanQueueService = Depends(get_kanban_queue_service),
) -> List[KanbanJobDTO]:
    """List and filter jobs."""
    return service.list_jobs(chat_id, status=status_filter, stage=stage_filter, assignee=assignee)


@router.get("/jobs/{job_id}", response_model=KanbanJobDTO)
async def get_job(
    chat_id: str,
    job_id: str,
    service: PersistentKanbanQueueService = Depends(get_kanban_queue_service),
) -> KanbanJobDTO:
    """Retrieve single job details."""
    job = service.get_job(chat_id, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found")
    return job


@router.post("/jobs/{job_id}/claim", response_model=KanbanJobDTO)
async def claim_job(
    chat_id: str,
    job_id: str,
    req: ClaimKanbanJobRequest,
    service: PersistentKanbanQueueService = Depends(get_kanban_queue_service),
) -> KanbanJobDTO:
    """Claim a READY job and begin RUNNING."""
    try:
        return service.claim_job(chat_id, job_id, req.assignee)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/complete", response_model=KanbanJobDTO)
async def complete_job(
    chat_id: str,
    job_id: str,
    req: CompleteKanbanJobRequest,
    service: PersistentKanbanQueueService = Depends(get_kanban_queue_service),
) -> KanbanJobDTO:
    """Complete a job and unblock downstream dependencies."""
    try:
        return service.complete_job(chat_id, job_id, req.summary, req.metadata)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/block", response_model=KanbanJobDTO)
async def block_job(
    chat_id: str,
    job_id: str,
    req: BlockKanbanJobRequest,
    service: PersistentKanbanQueueService = Depends(get_kanban_queue_service),
) -> KanbanJobDTO:
    """Mark a job as BLOCKED."""
    try:
        return service.block_job(chat_id, job_id, req.reason)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/unblock", response_model=KanbanJobDTO)
async def unblock_job(
    chat_id: str,
    job_id: str,
    service: PersistentKanbanQueueService = Depends(get_kanban_queue_service),
) -> KanbanJobDTO:
    """Unblock a job."""
    try:
        return service.unblock_job(chat_id, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/heartbeat")
async def heartbeat_job(
    chat_id: str,
    job_id: str,
    service: PersistentKanbanQueueService = Depends(get_kanban_queue_service),
) -> dict[str, bool]:
    """Send heartbeat for a running worker."""
    ok = service.heartbeat_job(chat_id, job_id)
    return {"success": ok}


@router.post("/jobs/{job_id}/comments", response_model=KanbanCommentDTO)
async def add_comment(
    chat_id: str,
    job_id: str,
    req: AddCommentRequest,
    service: PersistentKanbanQueueService = Depends(get_kanban_queue_service),
) -> KanbanCommentDTO:
    """Add comment and synchronize with Swarm blackboard if tagged."""
    try:
        return service.add_comment(chat_id, job_id, req.author, req.content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/link")
async def link_dependency(
    chat_id: str,
    req: LinkDependencyRequest,
    service: PersistentKanbanQueueService = Depends(get_kanban_queue_service),
) -> dict[str, bool]:
    """Add a directed acyclic dependency link between jobs."""
    ok = service.link_dependency(chat_id, req.from_job_id, req.to_job_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to link jobs: invalid IDs or cycle detected",
        )
    return {"linked": True}


@router.post("/specify", response_model=SpecifyPromptResponse)
async def specify_prompt(
    chat_id: str,
    req: SpecifyPromptRequest,
    service: PersistentKanbanQueueService = Depends(get_kanban_queue_service),
) -> SpecifyPromptResponse:
    """Auto-triage specify a raw prompt into title, goal, approach, and criteria."""
    return service.specify_prompt(chat_id, req.prompt)


@router.post("/jobs/{job_id}/decompose", response_model=List[KanbanJobDTO])
async def decompose_job(
    chat_id: str,
    job_id: str,
    req: DecomposeJobRequest,
    service: PersistentKanbanQueueService = Depends(get_kanban_queue_service),
) -> List[KanbanJobDTO]:
    """Fan-out decompose a parent job into subtasks."""
    try:
        subtasks_data = [
            {"title": s.title, "goal": s.goal, "approach": s.approach, "assignee": s.assignee or ""}
            for s in req.subtasks
        ]
        return service.decompose_job(chat_id, job_id, subtasks_data)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/circuit-breaker")
async def toggle_circuit_breaker(
    chat_id: str,
    req: ToggleCircuitBreakerRequest,
    service: PersistentKanbanQueueService = Depends(get_kanban_queue_service),
) -> dict[str, bool]:
    """Toggle auto_decompose safety circuit breaker."""
    enabled = service.toggle_circuit_breaker(chat_id, req.enabled)
    return {"auto_decompose_enabled": enabled}


@router.post("/reclaim-stale")
async def reclaim_stale_workers(
    chat_id: str,
    service: PersistentKanbanQueueService = Depends(get_kanban_queue_service),
) -> dict[str, List[str]]:
    """Scan and reclaim stale workers exceeding heartbeat threshold."""
    reclaimed = service.reclaim_stale_workers(chat_id)
    return {"reclaimed_job_ids": reclaimed}


@router.get("/blackboard", response_model=List[BlackboardEntryDTO])
async def get_blackboard(
    chat_id: str,
    stage: Optional[SwarmTopologyStageEnum] = Query(None),
    service: PersistentKanbanQueueService = Depends(get_kanban_queue_service),
) -> List[BlackboardEntryDTO]:
    """Get entries from Swarm shared blackboard."""
    return service.get_blackboard(chat_id, stage=stage)


@router.post("/batch/dispatch", response_model=DispatchWaveResponseDTO)
async def dispatch_wave(
    chat_id: str,
    req: DispatchWaveRequest,
    service: PersistentKanbanQueueService = Depends(get_kanban_queue_service),
) -> DispatchWaveResponseDTO:
    """Dispatch parallel wave across ready jobs."""
    return service.dispatch_wave(chat_id, max_parallel=req.max_parallel, strategy=req.distribution_strategy)


@router.get("/batch/status", response_model=BatchRunnerStatusDTO)
async def get_batch_status(
    chat_id: str,
    service: PersistentKanbanQueueService = Depends(get_kanban_queue_service),
) -> BatchRunnerStatusDTO:
    """Get 12-way batch runner checkpoint and execution status."""
    return service.get_batch_status(chat_id)


@router.get("/batch/trajectories")
async def export_trajectories(
    chat_id: str,
    service: PersistentKanbanQueueService = Depends(get_kanban_queue_service),
) -> dict[str, str]:
    """Export HuggingFace compatible JSONL trajectories."""
    jsonl = service.export_trajectories(chat_id)
    return {"trajectories_jsonl": jsonl}
