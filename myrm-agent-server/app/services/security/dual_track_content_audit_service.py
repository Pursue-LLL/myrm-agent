"""
[POS] app/services/security/dual_track_content_audit_service.py
[INPUT] myrm_agent_harness.core.security.dual_track_content_audit, app.schemas.dual_track_content_audit
[OUTPUT] DualTrackContentAuditService, get_dual_track_content_audit_service

Thread-safe service managing decoupled asynchronous stream mirroring, out-of-band compliance
auditing, and real-time stream circuit-breaking.

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import threading
from typing import Optional

from myrm_agent_harness.core.security.dual_track_content_audit import (
    AuditVerdict,
    CircuitBreakerSignal,
    DualTrackContentAuditSuite,
)

from app.schemas.dual_track_content_audit import (
    AuditVerdictResponse,
    BreakerStatusResponse,
    CircuitBreakerActionEnum,
    CircuitBreakerSignalResponse,
    ContentRiskLevelEnum,
    DualTrackMetricsResponse,
    MirrorChunkRequest,
    MirrorChunkResponse,
    ResetBreakerRequest,
    ResetBreakerResponse,
    ScanTextRequest,
    ScanTextResponse,
    ViolationCategoryEnum,
)


class DualTrackContentAuditService:
    """Service orchestrating decoupled out-of-band streaming audits and circuit breaker trips."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._suite = DualTrackContentAuditSuite()

    def mirror_chunk(self, req: MirrorChunkRequest) -> MirrorChunkResponse:
        """Mirror streaming chunk to out-of-band compliance pipeline and check circuit breaker."""
        with self._lock:
            verdict, signal = self._suite.mirror_chunk(
                session_id=req.session_id,
                text_chunk=req.text_chunk,
                sequence_no=req.sequence_no,
                is_final=req.is_final,
            )
            is_tripped = self._suite.is_session_tripped(req.session_id)

        verdict_resp = self._to_verdict_response(verdict)
        signal_resp = self._to_signal_response(signal) if signal is not None else None

        return MirrorChunkResponse(
            verdict=verdict_resp,
            circuit_breaker_signal=signal_resp,
            is_tripped=is_tripped,
        )

    def scan_text(self, req: ScanTextRequest) -> ScanTextResponse:
        """Perform direct synchronous text compliance scan."""
        with self._lock:
            verdict = self._suite.scan_full_text(req.text)
        return ScanTextResponse(verdict=self._to_verdict_response(verdict))

    def get_breaker_status(self, session_id: str) -> BreakerStatusResponse:
        """Check whether a session's streaming conduit is halted by the circuit breaker."""
        with self._lock:
            is_tripped = self._suite.is_session_tripped(session_id)
            signal = self._suite.get_breaker_signal(session_id)

        signal_resp = self._to_signal_response(signal) if signal is not None else None
        return BreakerStatusResponse(
            session_id=session_id,
            is_tripped=is_tripped,
            signal=signal_resp,
        )

    def reset_breaker(self, req: ResetBreakerRequest) -> ResetBreakerResponse:
        """Reset a tripped circuit breaker for an interrupted session."""
        with self._lock:
            was_reset = self._suite.reset_breaker(req.session_id)
        return ResetBreakerResponse(
            session_id=req.session_id,
            was_reset=was_reset,
        )

    def get_metrics(self) -> DualTrackMetricsResponse:
        """Retrieve operational and telemetry metrics for the dual-track audit subsystem."""
        with self._lock:
            metrics = self._suite.get_metrics()
        return DualTrackMetricsResponse(
            total_chunks_mirrored=metrics.total_chunks_mirrored,
            total_violations_detected=metrics.total_violations_detected,
            total_breakers_tripped=metrics.total_breakers_tripped,
            active_monitored_sessions=metrics.active_monitored_sessions,
        )

    @staticmethod
    def _to_verdict_response(verdict: AuditVerdict) -> AuditVerdictResponse:
        return AuditVerdictResponse(
            is_violation=verdict.is_violation,
            risk_level=ContentRiskLevelEnum(verdict.risk_level.value),
            category=ViolationCategoryEnum(verdict.category.value),
            confidence=verdict.confidence,
            matched_pattern=verdict.matched_pattern,
            reason=verdict.reason,
        )

    @staticmethod
    def _to_signal_response(signal: CircuitBreakerSignal) -> CircuitBreakerSignalResponse:
        return CircuitBreakerSignalResponse(
            session_id=signal.session_id,
            trigger_sequence_no=signal.trigger_sequence_no,
            action=CircuitBreakerActionEnum(signal.action.value),
            category=ViolationCategoryEnum(signal.category.value),
            abort_frame=signal.abort_frame,
            reason=signal.reason,
            timestamp=signal.timestamp,
        )


_SERVICE_INSTANCE: Optional[DualTrackContentAuditService] = None
_SERVICE_LOCK = threading.Lock()


def get_dual_track_content_audit_service() -> DualTrackContentAuditService:
    """Get singleton instance of DualTrackContentAuditService."""
    global _SERVICE_INSTANCE
    with _SERVICE_LOCK:
        if _SERVICE_INSTANCE is None:
            _SERVICE_INSTANCE = DualTrackContentAuditService()
        return _SERVICE_INSTANCE
