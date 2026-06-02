"""Memory diagnostics API endpoints.

Exposes high-fidelity memory metrics, historical sampling, and on-demand
heap profiling capabilities from the Harness layer to the Frontend and Control Plane.

[INPUT]
- myrm_agent_harness.runtime.resource_monitor::get_resource_monitor (POS: Harness memory profiler)

[OUTPUT]
- GET /api/v1/health/memory/history: Get 512-point memory history
- POST /api/v1/health/memory/profile/start: Start heap profiling
- POST /api/v1/health/memory/profile/stop: Stop profiling and get top allocations

[POS]
Memory diagnostics API. Provides observability for memory leaks and OOM prevention.
"""

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.runtime.resource_monitor import get_resource_monitor

from app.services.chat.conversation_search_service import ConversationSearchService

router = APIRouter(prefix="/memory", tags=["Health & Diagnostics"])


@router.get("/history")
async def get_memory_history() -> dict[str, object]:
    """Get the 512-point historical memory sampling data."""
    monitor = get_resource_monitor()
    history = monitor.get_history()
    return {"history": history}


@router.post("/profile/start")
async def start_memory_profiling(frames: int = 10) -> dict[str, object]:
    """Start heap profiling using tracemalloc.

    Warning: This will incur a ~10-20% performance overhead while active.
    """
    monitor = get_resource_monitor()
    started = monitor.start_profiling(frames=frames)
    if not started:
        raise HTTPException(status_code=400, detail="Profiling is already running")
    return {"status": "started", "message": "Heap profiling started successfully"}


@router.post("/profile/stop")
async def stop_memory_profiling() -> dict[str, object]:
    """Stop heap profiling and return the top memory allocations."""
    monitor = get_resource_monitor()
    try:
        top_allocations = monitor.stop_profiling()
        if not top_allocations:
            raise HTTPException(status_code=400, detail="Profiling was not running")
        return {"status": "stopped", "top_allocations": top_allocations}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop profiling: {e}") from e


@router.get("/conversation-recall")
async def get_conversation_recall_health() -> dict[str, object]:
    """Return opaque Conversation Recall index health without exposing conversation text."""
    return await ConversationSearchService.health()
