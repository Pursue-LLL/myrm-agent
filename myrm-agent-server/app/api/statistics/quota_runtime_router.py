"""Runtime search quota and browser compute telemetry API endpoints.

[INPUT]
- app.services.observability.runtime_meter_service::runtime_meter_service
- app.database.connection::get_session

[OUTPUT]
- GET /statistics/search-quotas
- POST /statistics/search-quotas/record
- GET /statistics/browser-runtime
- POST /statistics/browser-runtime/record

[POS]
REST API extension router exposing operational telemetry: search provider quotas and browser compute costs.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.errors import internal_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.services.observability.runtime_meter_service import runtime_meter_service

router = APIRouter(prefix="", tags=["runtime-meter"])
logger = logging.getLogger(__name__)


class SearchQuotaRecordRequest(BaseModel):
    provider: str = Field(..., min_length=1, max_length=32)
    count: int = Field(default=1, ge=1, le=1000)
    quota_exceeded: bool = False


class SearchQuotaResetRequest(BaseModel):
    provider: str | None = Field(default=None, max_length=32)


class SearchQuotaLimitUpdateRequest(BaseModel):
    provider: str = Field(..., min_length=1, max_length=32)
    quota_limit: int = Field(..., ge=1, le=10_000_000)


class BrowserRuntimeRecordRequest(BaseModel):
    session_id: str | None = Field(default=None, max_length=128)
    duration_seconds: float = Field(default=0.0, ge=0.0)
    active_compute_seconds: float = Field(default=0.0, ge=0.0)
    bytes_transferred: int = Field(default=0, ge=0)
    request_count: int = Field(default=0, ge=0)
    failed_request_count: int = Field(default=0, ge=0)


@router.get("/search-quotas")
async def get_search_quotas(session: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Retrieve all search provider quota statuses with progressive warning levels."""
    try:
        data = await runtime_meter_service.get_search_quotas(session)
        return success_response(data)
    except Exception as exc:
        logger.error("Failed to query search quotas: %s", exc, exc_info=True)
        raise internal_error("Failed to retrieve search quotas", exception=exc) from exc


@router.post("/search-quotas/record")
async def record_search_quota(
    req: SearchQuotaRecordRequest,
    session: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Record search usage or trigger self-healing 429 recalibration."""
    try:
        record = await runtime_meter_service.record_search_usage(
            session,
            provider=req.provider,
            count=req.count,
            quota_exceeded=req.quota_exceeded,
        )
        return success_response(
            {
                "provider": record.provider,
                "used_count": record.used_count,
                "quota_limit": record.quota_limit,
                "is_depleted": record.is_depleted,
            }
        )
    except Exception as exc:
        logger.error("Failed to record search quota: %s", exc, exc_info=True)
        raise internal_error("Failed to record search quota", exception=exc) from exc


@router.get("/browser-runtime")
async def get_browser_runtime_summary(session: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Retrieve monthly browser automation compute and network transfer summary."""
    try:
        summary = await runtime_meter_service.get_browser_runtime_summary(session)
        return success_response(summary)
    except Exception as exc:
        logger.error("Failed to retrieve browser runtime summary: %s", exc, exc_info=True)
        raise internal_error("Failed to retrieve browser runtime summary", exception=exc) from exc


@router.post("/browser-runtime/record")
async def record_browser_runtime(
    req: BrowserRuntimeRecordRequest,
    session: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Ingest session-level browser telemetry record."""
    try:
        record = await runtime_meter_service.record_browser_runtime(
            session,
            duration_seconds=req.duration_seconds,
            active_compute_seconds=req.active_compute_seconds,
            bytes_transferred=req.bytes_transferred,
            request_count=req.request_count,
            failed_request_count=req.failed_request_count,
            session_id=req.session_id,
        )
        return success_response({"id": record.id, "year_month": record.year_month})
    except Exception as exc:
        logger.error("Failed to record browser runtime: %s", exc, exc_info=True)
        raise internal_error("Failed to record browser runtime", exception=exc) from exc from exc


@router.get("/runtime-cost-gauge")
async def get_runtime_cost_gauge(
    session: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Get integrated operational cost, search quota, and browser compute gauge."""
    try:
        gauge = await runtime_meter_service.get_runtime_burn_rate_gauge(session)
        return success_response(gauge)
    except Exception as exc:
        logger.error("Failed to get runtime cost gauge: %s", exc, exc_info=True)
        raise internal_error("Failed to get runtime cost gauge", exception=exc) from exc



@router.post("/search-quotas/reset")
async def reset_search_quota(
    req: SearchQuotaResetRequest,
    session: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Reset used count and depletion status for one or all providers."""
    try:
        reset_count = await runtime_meter_service.reset_search_quota(session, provider=req.provider)
        return success_response({"reset_records_count": reset_count, "provider": req.provider})
    except Exception as exc:
        logger.error("Failed to reset search quota: %s", exc, exc_info=True)
        raise internal_error("Failed to reset search quota", exception=exc) from exc


@router.put("/search-quotas/limit")
async def update_search_quota_limit(
    req: SearchQuotaLimitUpdateRequest,
    session: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Update custom quota limit for a specific search provider."""
    try:
        record = await runtime_meter_service.update_search_quota_limit(
            session,
            provider=req.provider,
            quota_limit=req.quota_limit,
        )
        return success_response(
            {
                "provider": record.provider,
                "quota_limit": record.quota_limit,
                "used_count": record.used_count,
            }
        )
    except Exception as exc:
        logger.error("Failed to update search quota limit: %s", exc, exc_info=True)
        raise internal_error("Failed to update search quota limit", exception=exc) from exc from exc
