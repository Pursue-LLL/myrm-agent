"""Harness integration APIs for Task-Adaptive Context."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from myrm_agent_harness.agent.middlewares.approval import get_event_logger

from app.core.utils.response_utils import success_response
from app.database.standard_responses import StandardSuccessResponse

router = APIRouter()


@router.get("/task-adaptive/recent", response_model=StandardSuccessResponse)
async def get_recent_task_adaptive_contexts(limit: int = 10) -> JSONResponse:
    """Retrieve recent Task-Adaptive Contexts (TraceRunDigests) for UI preview.

    This powers the 'Kanban JIT Preview' where users can select
    historical context to hydrate a new session.
    """
    try:
        logger = get_event_logger()
        if not logger or not logger._backend:
            return success_response(data={"digests": []})

        # Get recent sessions
        session_ids = await logger._backend.get_all_session_ids()
        target_sids = session_ids[-limit:] if session_ids else []

        from myrm_agent_harness.agent.event_log.types import EventFilter

        digests = []
        for sid in reversed(target_sids):  # Newest first
            events = await logger._backend.get_events(sid, EventFilter(event_types=frozenset({"trace_run_digest"})))
            if events:
                # The latest digest for this session
                latest_event = max(events, key=lambda e: e.timestamp)
                digests.append(latest_event.data)

        return success_response(data={"digests": digests})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
