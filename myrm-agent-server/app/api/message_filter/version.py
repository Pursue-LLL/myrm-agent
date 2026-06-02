"""Message filter version history API endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.services.message_filter import ConfigVersionService

logger = logging.getLogger(__name__)

router = APIRouter()


class VersionHistoryResponse(BaseModel):
    """Response schema for version history entry."""

    id: int
    version: int
    config: dict[str, object]
    updated_by: str | None
    updated_at: str


class RollbackRequest(BaseModel):
    """Request schema for version rollback."""

    version: int = Field(..., description="Version number to rollback to")
    updated_by: str | None = Field(None, description="User performing the rollback")


class RollbackResponse(BaseModel):
    """Response schema for rollback operation."""

    version: int
    success: bool
    message: str


@router.get("/history", response_model=list[VersionHistoryResponse])
async def get_version_history(
    limit: int = Query(50, ge=1, le=200, description="Maximum number of entries"),
    offset: int = Query(0, ge=0, description="Number of entries to skip"),
    db: AsyncSession = Depends(get_db),
) -> list[VersionHistoryResponse]:
    """Get configuration version history.

    Args:
        limit: Maximum number of entries to return
        offset: Number of entries to skip
        db: Database session

    Returns:
        List of version history entries
    """
    try:
        version_service = ConfigVersionService(db)
        history = await version_service.get_history(limit=limit, offset=offset)

        return [
            VersionHistoryResponse(
                id=entry.id,
                version=entry.version,
                config=entry.config,
                updated_by=entry.updated_by,
                updated_at=entry.updated_at.isoformat(),
            )
            for entry in history
        ]
    except Exception as e:
        logger.error(f"Failed to get version history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get version history") from e


@router.post("/rollback", response_model=RollbackResponse)
async def rollback_version(
    rollback_data: RollbackRequest,
    db: AsyncSession = Depends(get_db),
) -> RollbackResponse:
    """Rollback configuration to a previous version.

    Args:
        rollback_data: Rollback request data
        db: Database session

    Returns:
        Rollback operation result
    """
    try:
        version_service = ConfigVersionService(db)
        config = await version_service.rollback_to_version(
            version=rollback_data.version,
            updated_by=rollback_data.updated_by,
        )

        if config is None:
            return RollbackResponse(
                version=rollback_data.version,
                success=False,
                message=f"Version {rollback_data.version} not found",
            )

        await db.commit()
        return RollbackResponse(
            version=rollback_data.version,
            success=True,
            message=f"Successfully rolled back to version {rollback_data.version}",
        )
    except Exception as e:
        logger.error(f"Failed to rollback to version {rollback_data.version}: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to rollback configuration") from e
