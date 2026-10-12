"""Unit tests for AuditCoverageService."""

from __future__ import annotations

import pytest
from myrm_agent_harness.core.security.audit_coverage import (
    UnsupportedFindingError,
)

from app.schemas.audit_coverage import (
    ApplicationModelDto,
    AttachRepairBundleRequest,
    AuditFindingDto,
    CoverageScopeItemDto,
    InitializeAuditSessionRequest,
    RecordFindingRequest,
    RepairPatchDto,
)
from app.services.security.audit_coverage_service import AuditCoverageService


@pytest.fixture
def sample_service() -> AuditCoverageService:
    service = AuditCoverageService()
    req = InitializeAuditSessionRequest(
        application_model=ApplicationModelDto(
            name="CheckoutService",
            tech_stack=["Python 3.13", "FastAPI"],
            entrypoints=["/api/v1/checkout", "/api/v1/pay"],
            trust_boundaries=["Client -> Gateway", "Gateway -> DB"],
            data_flows=["Card info flow", "Receipt dispatch"],
            supported_finding_categories=[
                "AUTH_ACCESS_CONTROL",
                "SECRET_LEAKAGE",
            ],
        ),
        scopes=[
            CoverageScopeItemDto(
                category="AUTH_ACCESS_CONTROL",
                status="COVERED",
                audit_surface="Checked JWT authorization on all endpoints",
                coverage_percentage=100.0,
            )
        ],
    )
    service.initialize_session(req)
    return service


def test_session_initialization_and_coverage_report(
    sample_service: AuditCoverageService,
) -> None:
    report = sample_service.get_coverage_report()
    assert report.application_model.name == "CheckoutService"
    assert len(report.scopes) == 6  # 6 standard coverage categories
    # Secret leakage was not explicitly provided, so it is uncovered
    secret_scope = next(s for s in report.scopes if s.category == "SECRET_LEAKAGE")
    assert secret_scope.status == "UNCOVERED_UNSUPPORTED"
    assert secret_scope.coverage_percentage == 0.0


def test_record_finding_and_adversarial_challenge(
    sample_service: AuditCoverageService,
) -> None:
    finding_req = RecordFindingRequest(
        finding=AuditFindingDto(
            finding_id="find_sec_1",
            category="SECRET_LEAKAGE",
            severity="HIGH",
            title="Hardcoded payment secret",
            description="Detected API secret string in source",
            application_model_ref="/api/v1/pay",
            evidence="PAY_SECRET = 'secret_val'",
        ),
        codebase_context="PAY_SECRET = os.environ.get('PAY_SECRET')",
    )

    recorded = sample_service.record_finding(finding_req)
    assert recorded.finding_id == "find_sec_1"
    assert recorded.challenge_status == "CHALLENGED_CONFIRMED"


def test_unsupported_finding_rejected_by_model_contract(
    sample_service: AuditCoverageService,
) -> None:
    finding_req = RecordFindingRequest(
        finding=AuditFindingDto(
            finding_id="find_invalid",
            category="CONCURRENCY_STATE_INTEGRITY",  # Not in supported_finding_categories
            severity="MEDIUM",
            title="Concurrency lock missing",
            description="No distributed lock found",
            application_model_ref="/api/v1/checkout",
            evidence="counter += 1",
        )
    )

    with pytest.raises(UnsupportedFindingError, match="outside the supported categories"):
        sample_service.record_finding(finding_req)


def test_attach_and_verify_repair_bundle(sample_service: AuditCoverageService) -> None:
    # First record a valid finding
    sample_service.record_finding(
        RecordFindingRequest(
            finding=AuditFindingDto(
                finding_id="find_auth_1",
                category="AUTH_ACCESS_CONTROL",
                severity="CRITICAL",
                title="Bypassed token verification",
                description="Token verify function not called",
                application_model_ref="/api/v1/checkout",
                evidence="def checkout(): return ok",
            )
        )
    )

    # Attach replayable repair bundle
    bundle_req = AttachRepairBundleRequest(
        finding_id="find_auth_1",
        patches=[
            RepairPatchDto(
                file_path="app/checkout.py",
                target_checksum="hash_chk",
                diff_content="+ verify_jwt(request)",
                replay_command="git apply patch.diff",
            )
        ],
        replay_script="pytest tests/test_checkout.py",
        verify_immediately=True,
    )

    bundle = sample_service.attach_repair_bundle(bundle_req)
    assert bundle.is_verified is True
    assert bundle.finding_id == "find_auth_1"
    assert bundle.checksum != ""

    # Check that finding is updated to TESTED in report
    report = sample_service.get_coverage_report()
    assert len(report.findings) == 1
    assert report.findings[0].verification_tier == "TESTED"
    assert len(report.repair_bundles) == 1
