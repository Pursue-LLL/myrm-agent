"""
[POS] tests/unit/test_dual_track_content_audit_service.py
[INPUT] app.schemas.dual_track_content_audit, app.services.security.dual_track_content_audit_service
[OUTPUT] unit tests

Tests for DualTrackContentAuditService logic.
Strict typing applied: No `Any` types allowed.
"""

from app.schemas.dual_track_content_audit import (
    CircuitBreakerActionEnum,
    ContentRiskLevelEnum,
    MirrorChunkRequest,
    ResetBreakerRequest,
    ScanTextRequest,
    ViolationCategoryEnum,
)
from app.services.security.dual_track_content_audit_service import (
    DualTrackContentAuditService,
)


def test_service_mirror_chunk_and_circuit_breaker() -> None:
    service = DualTrackContentAuditService()
    session_id = "sess-dt-001"

    # 1. Normal safe chunk
    req1 = MirrorChunkRequest(
        session_id=session_id,
        sequence_no=1,
        text_chunk="Hello, this is a clean business discussion. ",
    )
    res1 = service.mirror_chunk(req1)
    assert res1.verdict.is_violation is False
    assert res1.is_tripped is False
    assert res1.circuit_breaker_signal is None

    # 2. Critical violation chunk (API key leak)
    req2 = MirrorChunkRequest(
        session_id=session_id,
        sequence_no=2,
        text_chunk="Your secret token is ghp_999988887777666655554444333322221111",
    )
    res2 = service.mirror_chunk(req2)
    assert res2.verdict.is_violation is True
    assert res2.verdict.risk_level == ContentRiskLevelEnum.CRITICAL
    assert res2.verdict.category == ViolationCategoryEnum.CREDENTIAL_LEAK
    assert res2.is_tripped is True
    assert res2.circuit_breaker_signal is not None
    assert res2.circuit_breaker_signal.action == CircuitBreakerActionEnum.TRIP_AND_ABORT
    assert "[STREAM_ABORT_SAFETY_VIOLATION:" in res2.circuit_breaker_signal.abort_frame

    # 3. Check breaker status
    status = service.get_breaker_status(session_id)
    assert status.is_tripped is True
    assert status.signal is not None

    # 4. Reset breaker
    reset_res = service.reset_breaker(ResetBreakerRequest(session_id=session_id))
    assert reset_res.was_reset is True
    assert service.get_breaker_status(session_id).is_tripped is False


def test_service_scan_text_sync() -> None:
    service = DualTrackContentAuditService()
    # Safe text
    safe_res = service.scan_text(ScanTextRequest(text="Regular text without any violations"))
    assert safe_res.verdict.is_violation is False

    # Violation text
    bad_res = service.scan_text(ScanTextRequest(text="-----BEGIN PRIVATE KEY-----\nMIIEowIBAAKCAQEA"))
    assert bad_res.verdict.is_violation is True
    assert bad_res.verdict.category == ViolationCategoryEnum.CREDENTIAL_LEAK


def test_service_metrics() -> None:
    service = DualTrackContentAuditService()
    service.mirror_chunk(
        MirrorChunkRequest(
            session_id="sess-m1",
            sequence_no=1,
            text_chunk="Clean text",
        )
    )
    metrics = service.get_metrics()
    assert metrics.total_chunks_mirrored == 1
    assert metrics.total_violations_detected == 0
