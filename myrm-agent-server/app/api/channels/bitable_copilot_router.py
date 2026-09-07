"""Bitable & Spreadsheet Sidebar Interactive CoPilot Router.

[INPUT]
- app.services.bitable_copilot.engine::DataWranglingEngine
- app.services.bitable_copilot.models::TableContextPayload, BatchWranglingResult
- fastapi::APIRouter, HTTPException, Depends
- app.api.dependencies::get_deploy_identity

[OUTPUT]
- router: Fast REST API router for sidebar data wrangling and cell mutation proposals.

[POS]
API route in app/api/channels/bitable_copilot_router.py.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.dependencies import get_deploy_identity
from app.services.bitable_copilot.engine import DataWranglingEngine
from app.services.bitable_copilot.models import (
    BatchWranglingResult,
    TableContextPayload,
)

logger = logging.getLogger("myrm.api.channels.bitable_copilot")

router = APIRouter(
    prefix="/channels/bitable-copilot",
    tags=["bitable-copilot"],
)

_engine = DataWranglingEngine()


class WrangleRequest(BaseModel):
    """Request payload for table data wrangling."""

    context: TableContextPayload = Field(..., description="Active table schema and rows")
    instruction: str = Field(..., min_length=1, max_length=2000, description="User instruction prompt")


@router.post(
    "/wrangle",
    response_model=BatchWranglingResult,
    summary="Batch process table rows and return proposed cell mutations",
)
async def wrangle_table_data(
    req: WrangleRequest,
    _identity: Optional[dict[str, object]] = Depends(get_deploy_identity),
) -> BatchWranglingResult:
    """Process table rows with natural language instruction and generate diff proposals.

    Returns:
        BatchWranglingResult containing list of cell mutations with reasoning.
    """
    if not req.context.fields:
        raise HTTPException(status_code=400, detail="Table context must contain at least one field schema")
    
    try:
        result = _engine.process_table_instruction(
            context=req.context,
            instruction=req.instruction,
        )
        return result
    except Exception as exc:
        logger.exception("Failed to process table data wrangling: %s", exc)
        raise HTTPException(status_code=500, detail=f"Data wrangling failed: {exc}") from exc
