"""[POS]: app/api/memory/tool_backup.py
[INPUT]: HTTP requests for durable tool use side-index recording, query, and audit statistics.
[OUTPUT]: FastAPI APIRouter endpoints managing durable tool execution audit persistence.
"""

from fastapi import APIRouter, Depends, HTTPException
from myrm_agent_harness.toolkits.memory import (
    ToolUseBackupService,
    ToolUseQueryFilter,
    ToolUseRecord,
    ToolUseStatus,
)

from app.schemas.tool_backup import (
    QueryToolUsesRequest,
    QueryToolUsesResponse,
    RecordToolUseRequest,
    RecordToolUseResponse,
    ToolUseItemResponse,
    ToolUseStatsResponse,
)
from app.services.memory.tool_backup import get_tool_backup_service

router = APIRouter(prefix="/tool-backup", tags=["tool_backup"])


def _to_item_response(rec: ToolUseRecord) -> ToolUseItemResponse:
    return ToolUseItemResponse(
        id=rec.id,
        session_id=rec.session_id,
        tool_name=rec.tool_name,
        tool_call_id=rec.tool_call_id,
        raw_input=rec.raw_input,
        raw_output=rec.raw_output,
        status=str(rec.status),
        duration_ms=rec.duration_ms,
        created_at_epoch=rec.created_at_epoch,
        is_truncated=rec.is_truncated,
        original_output_bytes=rec.original_output_bytes,
        metadata=rec.metadata,
    )


@router.post("/record", response_model=RecordToolUseResponse)
def record_tool_use(
    req: RecordToolUseRequest,
    service: ToolUseBackupService = Depends(get_tool_backup_service),
) -> RecordToolUseResponse:
    """Side-index a tool execution observation into durable SQLite storage."""
    status_enum = ToolUseStatus(req.status) if req.status in [s.value for s in ToolUseStatus] else ToolUseStatus.SUCCESS
    record = service.record_tool_use(
        session_id=req.session_id,
        tool_name=req.tool_name,
        raw_input=req.raw_input,
        raw_output=req.raw_output,
        tool_call_id=req.tool_call_id,
        status=status_enum,
        duration_ms=req.duration_ms,
        metadata=req.metadata,
    )
    if not record:
        raise HTTPException(status_code=500, detail="Failed to persist tool use backup")

    return RecordToolUseResponse(
        id=record.id,
        session_id=record.session_id,
        tool_name=record.tool_name,
        status=str(record.status),
        is_truncated=record.is_truncated,
        created_at_epoch=record.created_at_epoch,
    )


@router.post("/query", response_model=QueryToolUsesResponse)
def query_tool_uses(
    req: QueryToolUsesRequest,
    service: ToolUseBackupService = Depends(get_tool_backup_service),
) -> QueryToolUsesResponse:
    """Query durable tool execution records by session, tool name, or outcome."""
    status_enum = (
        ToolUseStatus(req.status)
        if req.status and req.status in [s.value for s in ToolUseStatus]
        else None
    )
    filter_spec = ToolUseQueryFilter(
        session_id=req.session_id,
        tool_name=req.tool_name,
        status=status_enum,
        limit=req.limit,
        offset=req.offset,
    )
    records = service.query_tool_uses(filter_spec)
    items = [_to_item_response(r) for r in records]
    return QueryToolUsesResponse(items=items, total=len(items))


@router.get("/stats", response_model=ToolUseStatsResponse)
def get_tool_use_stats(
    session_id: str | None = None,
    service: ToolUseBackupService = Depends(get_tool_backup_service),
) -> ToolUseStatsResponse:
    """Retrieve tool execution invocation volume, success rate, and duration metrics."""
    stats = service.get_stats(session_id=session_id)
    return ToolUseStatsResponse(
        total_tool_uses=stats.total_tool_uses,
        success_count=stats.success_count,
        error_count=stats.error_count,
        avg_duration_ms=stats.avg_duration_ms,
    )


@router.get("/{tool_use_id}", response_model=ToolUseItemResponse)
def get_tool_use(
    tool_use_id: str,
    service: ToolUseBackupService = Depends(get_tool_backup_service),
) -> ToolUseItemResponse:
    """Look up exact tool input and output observation by record ID."""
    record = service.get_tool_use(tool_use_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Tool use record '{tool_use_id}' not found")
    return _to_item_response(record)


@router.delete("/session/{session_id}")
def purge_session_tool_uses(
    session_id: str,
    service: ToolUseBackupService = Depends(get_tool_backup_service),
) -> dict[str, int | str]:
    """Purge all tool use side-index entries for a deleted session."""
    deleted_count = service.purge_session(session_id)
    return {"session_id": session_id, "deleted_count": deleted_count}
