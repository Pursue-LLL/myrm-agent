"""Message filter audit API endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.services.message_filter import AuditService

logger = logging.getLogger(__name__)

router = APIRouter()


class AuditLogResponse(BaseModel):
    """Response schema for audit log entry."""

    id: int
    user_id: str | None
    filter_type: str
    action: str
    reason: str | None
    metadata: dict[str, object]
    timestamp: str


class AuditStatsResponse(BaseModel):
    """Response schema for audit statistics."""

    total_events: int
    events_by_action: dict[str, int]
    events_by_filter: dict[str, int]


@router.get("", response_model=list[AuditLogResponse])
async def get_audit_logs(
    user_id: str | None = Query(None, description="Filter by user ID"),
    filter_type: str | None = Query(None, description="Filter by filter type"),
    action: str | None = Query(None, description="Filter by action"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of entries"),
    offset: int = Query(0, ge=0, description="Number of entries to skip"),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLogResponse]:
    """Get message filter audit logs.

    Args:
        user_id: Filter by user ID (optional)
        filter_type: Filter by filter type (optional)
        action: Filter by action (optional)
        limit: Maximum number of entries to return
        offset: Number of entries to skip
        db: Database session

    Returns:
        List of audit log entries
    """
    try:
        _ = user_id  # reserved for future per-user audit filtering
        audit_service = AuditService(db)
        logs = await audit_service.get_logs(
            filter_type=filter_type,
            action=action,
            limit=limit,
            offset=offset,
        )

        out: list[AuditLogResponse] = []
        for log in logs:
            md_raw = log.metadata
            metadata: dict[str, object] = {str(k): v for k, v in md_raw.items()} if isinstance(md_raw, dict) else {}
            out.append(
                AuditLogResponse(
                    id=log.id,
                    user_id=None,
                    filter_type=log.filter_type,
                    action=log.action,
                    reason=log.reason,
                    metadata=metadata,
                    timestamp=log.timestamp.isoformat(),
                )
            )
        return out
    except Exception as e:
        logger.error(f"Failed to get audit logs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get audit logs") from e


@router.get("/stats", response_model=AuditStatsResponse)
async def get_audit_stats(
    user_id: str | None = Query(None, description="Filter by user ID"),
    filter_type: str | None = Query(None, description="Filter by filter type"),
    db: AsyncSession = Depends(get_db),
) -> AuditStatsResponse:
    """Get aggregated audit statistics.

    Args:
        user_id: Filter by user ID (optional)
        filter_type: Filter by filter type (optional)
        db: Database session

    Returns:
        Audit statistics
    """
    try:
        _ = user_id
        audit_service = AuditService(db)
        stats = await audit_service.get_stats(filter_type=filter_type)

        return AuditStatsResponse(
            total_events=stats["total_events"],
            events_by_action=stats["events_by_action"],
            events_by_filter=stats["events_by_filter"],
        )
    except Exception as e:
        logger.error(f"Failed to get audit stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get audit stats") from e
