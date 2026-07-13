from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.schemas.streaming import SSE_RESPONSE_HEADERS
from app.services.agent.streaming_support.multiplexer import WorkspaceMultiplexer

from . import rules as workspace_rules

router = APIRouter()
router.include_router(workspace_rules.router)

@router.get("/stream")
async def workspace_stream() -> StreamingResponse:
    """Subscribe to the multiplexed workspace stream."""
    return StreamingResponse(
        content=WorkspaceMultiplexer.get().subscribe(),
        media_type="text/event-stream",
        headers=SSE_RESPONSE_HEADERS,
    )
