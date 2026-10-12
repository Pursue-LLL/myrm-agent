"""Service layer for Approval False Positive Metric Loop.

[INPUT]
- RecordVerdictRequest, SubmitVerdictFeedbackRequest.

[OUTPUT]
- RecordVerdictResponse, SubmitVerdictFeedbackResponse, GetFprMetricResponse, ExportFalsePositiveSamplesResponse.

[POS]
- Server service wrapping harness ApprovalMetricCollector for false positive telemetry and tuning feedback.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.approval_metrics import (
    ApprovalMetricCollector,
    ClassifierDecision,
    FeedbackOutcome,
)

from app.schemas.approval_metrics import (
    ExportFalsePositiveSamplesResponse,
    FalsePositiveSampleDto,
    GetFprMetricResponse,
    RecordVerdictRequest,
    RecordVerdictResponse,
    SubmitVerdictFeedbackRequest,
    SubmitVerdictFeedbackResponse,
)

logger = logging.getLogger(__name__)


class ApprovalMetricsService:
    """Manages classifier verdict telemetry, calculates empirical FPR, and exports tuning samples."""

    def __init__(self, default_alert_threshold: float = 0.05) -> None:
        self._collector = ApprovalMetricCollector(
            default_alert_threshold=default_alert_threshold
        )

    def record_verdict(self, request: RecordVerdictRequest) -> RecordVerdictResponse:
        """Record an immutable classifier decision log."""
        decision_enum = ClassifierDecision(request.decision)
        entry = self._collector.record_verdict(
            command=request.command,
            decision=decision_enum,
            reason=request.reason,
            workspace_root=request.workspace_root,
            taint_labels=request.taint_labels,
            timestamp=request.timestamp,
            audit_id=request.audit_id,
        )
        return RecordVerdictResponse(
            audit_id=entry.audit_id,
            timestamp=entry.timestamp,
            command=entry.command,
            decision=entry.decision.value,
            reason=entry.reason,
            feedback=entry.feedback.value,
        )

    def submit_feedback(
        self, request: SubmitVerdictFeedbackRequest
    ) -> SubmitVerdictFeedbackResponse:
        """Submit ground-truth human review feedback for a recorded verdict."""
        feedback_enum = FeedbackOutcome(request.feedback)
        success = self._collector.submit_feedback(
            audit_id=request.audit_id,
            feedback=feedback_enum,
            feedback_reason=request.feedback_reason,
        )
        return SubmitVerdictFeedbackResponse(
            success=success,
            audit_id=request.audit_id,
            feedback=request.feedback,
        )

    def get_metrics(
        self,
        window_seconds: float = 86400.0,
        alert_threshold: float | None = None,
    ) -> GetFprMetricResponse:
        """Calculate and return empirical false positive rate metrics."""
        metrics = self._collector.calculate_metrics(
            window_seconds=window_seconds,
            alert_threshold=alert_threshold,
        )
        return GetFprMetricResponse(
            window_seconds=metrics.window_seconds,
            total_evaluations=metrics.total_evaluations,
            total_blocks_or_asks=metrics.total_blocks_or_asks,
            confirmed_false_positives=metrics.confirmed_false_positives,
            confirmed_true_positives=metrics.confirmed_true_positives,
            false_positive_rate=metrics.false_positive_rate,
            alert_threshold=metrics.alert_threshold,
            is_alerting=metrics.is_alerting,
        )

    def export_false_positive_samples(
        self, limit: int = 50
    ) -> ExportFalsePositiveSamplesResponse:
        """Retrieve confirmed false positive samples to tune ALLOW exceptions and BLOCK rules."""
        raw_samples = self._collector.export_false_positive_samples(limit=limit)
        dtos = [
            FalsePositiveSampleDto(
                audit_id=s.audit_id,
                timestamp=s.timestamp,
                command=s.command,
                decision=s.decision.value,
                original_reason=s.original_reason,
                feedback_reason=s.feedback_reason,
                suggested_rule_tuning=s.suggested_rule_tuning,
            )
            for s in raw_samples
        ]
        return ExportFalsePositiveSamplesResponse(
            samples=dtos,
            total_count=len(dtos),
        )


_GLOBAL_SERVICE: ApprovalMetricsService | None = None


def get_approval_metrics_service() -> ApprovalMetricsService:
    """FastAPI dependency injection provider for ApprovalMetricsService."""
    global _GLOBAL_SERVICE
    if _GLOBAL_SERVICE is None:
        _GLOBAL_SERVICE = ApprovalMetricsService()
    return _GLOBAL_SERVICE
