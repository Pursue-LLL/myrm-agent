"""ROI and productivity time-saving analytics HTTP API endpoints.

[INPUT]
- fastapi::{APIRouter, Query, status}
- pydantic::{BaseModel, Field}
- app.services.analytics.roi_service::{
    RoiAnalyticsService,
    RoiMetricsSnapshot,
    HighYieldRoutineSpec,
    CategorySavingsItem,
  }

[OUTPUT]
- router: APIRouter for measurable agent ROI, daily hours saved HUD, and pre-packaged routines
- CalculateCustomRoiRequest, CalculateCustomRoiResponse

[POS]
app/api/system/roi_analytics_api.py - HTTP routes for AgentMeasurableRoiAndDailyTimeSavedHUD (Item 51 P0).
Strictly under 250 lines. Zero Any.
"""

from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from app.services.analytics.roi_service import (
    RoiAnalyticsService,
    RoiMetricsSnapshot,
    HighYieldRoutineSpec,
    CategorySavingsItem,
)

router = APIRouter(prefix="/system/roi", tags=["system-roi-analytics"])
_roi_service = RoiAnalyticsService()


class CalculateCustomRoiRequest(BaseModel):
    """Custom ROI calculation payload for ad-hoc batch tasks."""

    category_key: str = Field(..., description="Task category key")
    task_count: int = Field(1, ge=1, description="Number of automated tasks completed")
    actual_compute_cost_usd: float = Field(0.05, ge=0.0, description="Actual token cost in USD")
    hourly_rate_usd: float = Field(35.0, ge=1.0, description="Hourly wage baseline in USD")


class CalculateCustomRoiResponse(BaseModel):
    """Result of ad-hoc ROI calculation."""

    category_key: str
    task_count: int
    estimated_hours_saved: float
    estimated_saved_value_usd: float
    actual_compute_cost_usd: float
    roi_multiplier: float


@router.get(
    "/dashboard",
    response_model=RoiMetricsSnapshot,
    status_code=status.HTTP_200_OK,
    summary="Get aggregated ROI & daily hours saved dashboard metrics",
)
def get_roi_dashboard(
    time_range: str = Query("today", description="Time range: today | week | all_time"),
    hourly_rate: Optional[float] = Query(None, description="Optional baseline hourly rate in USD"),
) -> RoiMetricsSnapshot:
    """Retrieve measurable ROI metrics, total hours saved, and cost efficiency breakdown."""
    return _roi_service.get_dashboard_metrics(
        time_range=time_range,
        hourly_rate_override=hourly_rate,
    )


@router.get(
    "/routines",
    response_model=List[HighYieldRoutineSpec],
    status_code=status.HTTP_200_OK,
    summary="List curated high-yield out-of-the-box routine templates",
)
def list_high_yield_routines() -> List[HighYieldRoutineSpec]:
    """Retrieve pre-packaged high-yield workflows to eliminate blank-canvas onboarding friction."""
    return _roi_service.list_high_yield_routines()


@router.post(
    "/calculate",
    response_model=CalculateCustomRoiResponse,
    status_code=status.HTTP_200_OK,
    summary="Ad-hoc labor acceleration and ROI estimation calculation",
)
def calculate_custom_roi(payload: CalculateCustomRoiRequest) -> CalculateCustomRoiResponse:
    """Calculate instantaneous hours saved and ROI multiplier for a given workload."""
    bench = _roi_service.CATEGORY_LABOR_BENCHMARKS.get(
        payload.category_key,
        {"hours_per_unit": 1.5, "rate": payload.hourly_rate_usd},
    )
    hours_saved = round(payload.task_count * bench["hours_per_unit"], 2)
    saved_val = round(hours_saved * payload.hourly_rate_usd, 2)
    roi_mult = (
        round(saved_val / payload.actual_compute_cost_usd, 1)
        if payload.actual_compute_cost_usd > 0
        else 1.0
    )

    return CalculateCustomRoiResponse(
        category_key=payload.category_key,
        task_count=payload.task_count,
        estimated_hours_saved=hours_saved,
        estimated_saved_value_usd=saved_val,
        actual_compute_cost_usd=payload.actual_compute_cost_usd,
        roi_multiplier=roi_mult,
    )
