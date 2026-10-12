"""API router for Approval False Positive Metric Loop.

[INPUT]
- RecordVerdictRequest, SubmitVerdictFeedbackRequest.

[OUTPUT]
- RecordVerdictResponse, SubmitVerdictFeedbackResponse, GetFprMetricResponse, ExportFalsePositiveSamplesResponse.

[POS]
- Security router mounted under /security/approval-metrics.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.schemas.approval_metrics import (
    ExportFalsePositiveSamplesResponse,
    GetFprMetricResponse,
    RecordVerdictRequest,
    RecordVerdictResponse,
    SubmitVerdictFeedbackRequest,
    SubmitVerdictFeedbackResponse,
)
from app.services.security.approval_metrics_service import (
    ApprovalMetricsService,
    get_approval_metrics_service,
)

router = APIRouter(prefix="/approval-metrics", tags=["approval-metrics"])


@router.post("/verdict", response_model=RecordVerdictResponse)
async def record_classifier_verdict(
    request: RecordVerdictRequest,
    service: ApprovalMetricsService = Depends(get_approval_metrics_service),
) -> RecordVerdictResponse:
    """Record an immutable classifier decision log."""
    return service.record_verdict(request)


@router.post("/feedback", response_model=SubmitVerdictFeedbackResponse)
async def submit_verdict_feedback(
    request: SubmitVerdictFeedbackRequest,
    service: ApprovalMetricsService = Depends(get_approval_metrics_service),
) -> SubmitVerdictFeedbackResponse:
    """Submit operator or developer feedback on a blocked/interrupted action."""
    return service.submit_feedback(request)


@router.get("/metrics", response_model=GetFprMetricResponse)
async def get_fpr_metrics(
    window_seconds: float = Query(
        86400.0, ge=60.0, description="Evaluation sliding window in seconds"
    ),
    alert_threshold: float | None = Query(
        None, ge=0.0, le=1.0, description="Optional alert threshold override"
    ),
    service: ApprovalMetricsService = Depends(get_approval_metrics_service),
) -> GetFprMetricResponse:
    """Calculate empirical false positive rate and retrieve alert status."""
    return service.get_metrics(
        window_seconds=window_seconds,
        alert_threshold=alert_threshold,
    )


@router.get("/samples/false-positives", response_model=ExportFalsePositiveSamplesResponse)
async def export_false_positive_samples(
    limit: int = Query(50, ge=1, le=500, description="Maximum number of samples to export"),
    service: ApprovalMetricsService = Depends(get_approval_metrics_service),
) -> ExportFalsePositiveSamplesResponse:
    """Export confirmed false positive samples to tune ALLOW exceptions and BLOCK rules."""
    return service.export_false_positive_samples(limit=limit)
