"""
[INPUT]: Process node telemetry, orphan reaping requests, deadlock checks, and post-mortem logs.
[OUTPUT]: REST API endpoints exposing agent process trees, orphan process cascade termination, and deadlock breakers.
[POS]: myrm-agent/myrm-agent-server/app/api/system/runtime_zombie_reaper_api.py
"""

from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.runtime_zombie_reaper import (
    AgentRuntimeCausalityTracker,
    PostMortemTaskEntry,
    ProcessCausalityNode,
    ProcessLifecycleState,
    ProfileResourceUsage,
    RuntimeCausalitySnapshot,
)

router = APIRouter(prefix="/runtime-zombie-reaper", tags=["runtime-zombie-reaper"])

_default_tracker = AgentRuntimeCausalityTracker()


def get_default_causality_tracker() -> AgentRuntimeCausalityTracker:
    return _default_tracker


# --- Request/Response Models ---


class RegisterNodeRequest(BaseModel):
    node_id: str = Field(..., description="Unique node ID")
    name: str = Field(..., description="Node display name")
    role: str = Field(..., description="primary_agent | subagent | helper_process | sandbox_container")
    pid: int = Field(..., ge=0)
    pgid: int = Field(..., ge=0)
    parent_id: Optional[str] = Field(default=None)
    profile_id: str = Field(default="default")
    state: str = Field(default="running")
    cpu_percent: float = Field(default=0.0, ge=0.0)
    memory_rss_mb: float = Field(default=0.0, ge=0.0)
    tokens_consumed: int = Field(default=0, ge=0)
    exit_code: Optional[int] = Field(default=None)
    crash_reason: Optional[str] = Field(default=None)


class ReapOrphansRequest(BaseModel):
    parent_id: str = Field(..., description="Parent agent ID whose detached descendants must be reaped")
    reason: str = Field(default="Parent agent offline / detached")


class ReapOrphansResponse(BaseModel):
    parent_id: str
    reaped_count: int
    reaped_node_ids: List[str]


class DeadlockCheckResponse(BaseModel):
    parent_id: str
    child_id: str
    is_deadlocked: bool
    fault_message: Optional[str]


class RecordFailedTaskRequest(BaseModel):
    task_id: str
    name: str
    parent_task_id: Optional[str] = None
    profile_id: str = "default"
    exit_code: int
    crash_reason: str
    duration_ms: int = 0


# --- Endpoints ---


@router.get("/snapshot")
def get_runtime_snapshot() -> Dict[str, object]:
    """Retrieve full causality process tree snapshot, profile resource breakdown, and recent failed tasks."""
    tracker = get_default_causality_tracker()
    snapshot: RuntimeCausalitySnapshot = tracker.get_snapshot()
    return snapshot.model_dump()


@router.post("/register-node")
def register_node(req: RegisterNodeRequest) -> Dict[str, str]:
    """Register or update an active agent or auxiliary helper process node."""
    import time

    try:
        state_enum = ProcessLifecycleState(req.state.lower())
    except ValueError:
        state_enum = ProcessLifecycleState.RUNNING

    node = ProcessCausalityNode(
        node_id=req.node_id,
        name=req.name,
        role=req.role,
        pid=req.pid,
        pgid=req.pgid,
        parent_id=req.parent_id,
        profile_id=req.profile_id,
        state=state_enum,
        cpu_percent=req.cpu_percent,
        memory_rss_mb=req.memory_rss_mb,
        tokens_consumed=req.tokens_consumed,
        last_heartbeat_ms=int(time.time() * 1000),
        exit_code=req.exit_code,
        crash_reason=req.crash_reason,
    )
    tracker = get_default_causality_tracker()
    tracker.upsert_node(node)
    return {"status": "upserted", "node_id": req.node_id}


@router.post("/reap-orphans", response_model=ReapOrphansResponse)
def reap_orphans(req: ReapOrphansRequest) -> ReapOrphansResponse:
    """Watchdog trigger cascadingly terminating all orphan helper processes whose parent was detached."""
    tracker = get_default_causality_tracker()
    reaped_ids = tracker.reap_orphans(req.parent_id, req.reason)
    return ReapOrphansResponse(
        parent_id=req.parent_id,
        reaped_count=len(reaped_ids),
        reaped_node_ids=reaped_ids,
    )


@router.get("/check-deadlock", response_model=DeadlockCheckResponse)
def check_deadlock(
    parent_id: str = Query(..., description="Parent agent session ID"),
    child_id: str = Query(..., description="Subagent ID polled by parent"),
) -> DeadlockCheckResponse:
    """Actively detect if a child subagent has crashed, returning fault message to trip infinite polling."""
    tracker = get_default_causality_tracker()
    is_deadlocked, fault_msg = tracker.check_deadlock_polling(parent_id, child_id)
    return DeadlockCheckResponse(
        parent_id=parent_id,
        child_id=child_id,
        is_deadlocked=is_deadlocked,
        fault_message=fault_msg,
    )


@router.post("/record-failed-task")
def record_failed_task(req: RecordFailedTaskRequest) -> Dict[str, str]:
    """Archive a failed run for post-mortem root cause analysis."""
    import time

    entry = PostMortemTaskEntry(
        task_id=req.task_id,
        name=req.name,
        parent_task_id=req.parent_task_id,
        profile_id=req.profile_id,
        exit_code=req.exit_code,
        crash_reason=req.crash_reason,
        duration_ms=req.duration_ms,
        terminated_at_ms=int(time.time() * 1000),
    )
    tracker = get_default_causality_tracker()
    tracker.record_failed_task(entry)
    return {"status": "recorded", "task_id": req.task_id}


@router.post("/reset")
def reset_tracker() -> Dict[str, str]:
    """Reset the tracker state for isolated test execution."""
    tracker = get_default_causality_tracker()
    tracker.reset()
    return {"status": "reset"}
