"""
[POS] tests/unit/test_system_app_boundary_service.py
[INPUT] app.schemas.system_app_boundary, app.services.security.system_app_boundary_service
[OUTPUT] Unit tests for SystemAppBoundaryService
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from app.schemas.system_app_boundary import (
    AppAccessRequestDTO,
    GrantWriteConsentRequestDTO,
    RejectWriteConsentRequestDTO,
    SetScopeRuleRequestDTO,
)
from app.services.security.system_app_boundary_service import (
    SystemAppBoundaryService,
)


def test_service_read_access_scoping() -> None:
    """Test service enforcing declared container boundary for read-only requests."""
    service = SystemAppBoundaryService()
    service.set_scope_rule(
        SetScopeRuleRequestDTO(
            app_type="NOTES",
            allowed_containers=["Work Projects", "Meeting Notes"],
            allow_mutations_without_prompt=False,
        )
    )

    # 1. Permitted container
    v1 = service.evaluate_access(
        AppAccessRequestDTO(
            request_id="req-s-01",
            session_id="sess-01",
            app_type="NOTES",
            operation_type="READ_ONLY",
            target_container="Work Projects",
            payload_summary="Fetch project spec notes",
        )
    )
    assert v1.is_allowed is True
    assert v1.decision == "PERMITTED_SILENT"

    # 2. Blocked container
    v2 = service.evaluate_access(
        AppAccessRequestDTO(
            request_id="req-s-02",
            session_id="sess-01",
            app_type="NOTES",
            operation_type="READ_ONLY",
            target_container="Personal Health Record",
            payload_summary="Read health notes",
        )
    )
    assert v2.is_allowed is False
    assert v2.decision == "BOUNDARY_VIOLATION_BLOCKED"


def test_service_write_consent_approval_and_rejection() -> None:
    """Test mutation workflow requiring human consent, approval, and rejection."""
    service = SystemAppBoundaryService()
    service.set_scope_rule(
        SetScopeRuleRequestDTO(
            app_type="MAIL",
            allowed_containers=["Work Outbox"],
            allow_mutations_without_prompt=False,
        )
    )

    # Trigger consent requirement
    v_held = service.evaluate_access(
        AppAccessRequestDTO(
            request_id="req-mail-01",
            session_id="sess-02",
            app_type="MAIL",
            operation_type="MUTATE_WRITE",
            target_container="Work Outbox",
            payload_summary="Send client invoice email",
        )
    )
    assert v_held.is_allowed is False
    assert v_held.decision == "REQUIRE_WRITE_CONSENT"

    pending = service.list_pending_consents()
    assert len(pending) == 1
    assert pending[0].request_id == "req-mail-01"

    # Approve consent
    v_approved = service.grant_write_consent(
        GrantWriteConsentRequestDTO(
            request_id="req-mail-01",
            approver_note="Approved invoice dispatch",
        )
    )
    assert v_approved is not None
    assert v_approved.is_allowed is True
    assert v_approved.decision == "PERMITTED_SILENT"
    assert len(service.list_pending_consents()) == 0

    # Test rejection
    service.evaluate_access(
        AppAccessRequestDTO(
            request_id="req-mail-02",
            session_id="sess-02",
            app_type="MAIL",
            operation_type="MUTATE_WRITE",
            target_container="Work Outbox",
            payload_summary="Send mass marketing email",
        )
    )
    assert len(service.list_pending_consents()) == 1

    rejected = service.reject_write_consent(
        RejectWriteConsentRequestDTO(
            request_id="req-mail-02",
            reason="Spam risk",
        )
    )
    assert rejected is True
    assert len(service.list_pending_consents()) == 0


def test_service_emergency_lockdown_lifecycle() -> None:
    """Test emergency lockdown completely blocking access until lifted."""
    service = SystemAppBoundaryService()

    # Lockdown Photos
    service.lockdown_app("PHOTOS")

    v_blocked = service.evaluate_access(
        AppAccessRequestDTO(
            request_id="req-photo-lock",
            session_id="sess-03",
            app_type="PHOTOS",
            operation_type="READ_ONLY",
            target_container="Public",
            payload_summary="Search photos",
        )
    )
    assert v_blocked.is_allowed is False
    assert v_blocked.decision == "EMERGENCY_APP_LOCKED"

    # Unlock
    service.unlock_app("PHOTOS")
    v_restored = service.evaluate_access(
        AppAccessRequestDTO(
            request_id="req-photo-open",
            session_id="sess-03",
            app_type="PHOTOS",
            operation_type="READ_ONLY",
            target_container="Public",
            payload_summary="Search photos",
        )
    )
    assert v_restored.is_allowed is True


def test_service_audit_trail_and_metrics() -> None:
    """Test fetching chronological audit logs and telemetry metrics."""
    service = SystemAppBoundaryService()
    service.evaluate_access(
        AppAccessRequestDTO(
            request_id="req-aud",
            session_id="sess-04",
            app_type="CALENDAR",
            operation_type="READ_ONLY",
            target_container="Team Sync",
            payload_summary="Check team availability",
        )
    )

    trail = service.get_audit_trail(limit=10)
    assert len(trail) >= 1
    assert trail[-1].app_type == "CALENDAR"

    metrics = service.get_metrics()
    assert metrics.requests_evaluated_total >= 1
    assert metrics.silent_reads_permitted_total >= 1
