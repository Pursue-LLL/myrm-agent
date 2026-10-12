"""
[POS] tests/unit/test_enterprise_hipaa_compliance_service.py
Unit tests for EnterpriseHipaaComplianceService.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest

from app.schemas.enterprise_hipaa_compliance import (
    ExportCompliancePackageRequestDTO,
    PhiScreeningRequestDTO,
    RecordAuditEventRequestDTO,
    RegisterProviderRequestDTO,
    ValidateProviderEgressRequestDTO,
)
from app.services.security.enterprise_hipaa_compliance_service import (
    EnterpriseHipaaComplianceService,
)


@pytest.fixture
def service() -> EnterpriseHipaaComplianceService:
    return EnterpriseHipaaComplianceService()


def test_provider_management(service: EnterpriseHipaaComplianceService) -> None:
    # 1. Initially contains pre-configured compliant providers
    providers = service.list_providers()
    assert len(providers) >= 2
    assert any(p.provider_id == "azure-openai-enterprise-eastus" for p in providers)

    # 2. Register custom provider
    reg_req = RegisterProviderRequestDTO(
        provider_id="aws-bedrock-hipaa-west",
        provider_name="AWS Bedrock Claude (HIPAA BAA)",
        base_url="https://bedrock-runtime.us-west-2.amazonaws.com",
        tier="verified_baa_signed",
        baa_agreement_id="BAA-AMZN-2026-001",
        is_zero_training_mandated=True,
    )
    reg_res = service.register_provider(reg_req)
    assert reg_res.provider_id == "aws-bedrock-hipaa-west"
    assert reg_res.tier == "verified_baa_signed"

    # 3. Fetch provider
    fetched = service.get_provider("aws-bedrock-hipaa-west")
    assert fetched is not None
    assert fetched.baa_agreement_id == "BAA-AMZN-2026-001"

    # 4. Fetch non-existent
    assert service.get_provider("non-existent-id") is None


def test_audit_chain_recording_and_integrity(
    service: EnterpriseHipaaComplianceService,
) -> None:
    # 1. Record first event
    req1 = RecordAuditEventRequestDTO(
        event_type="agent_initiation",
        agent_id="agent-nurse-bot",
        session_id="encounter-session-001",
        action_summary="Spawned nurse bot with read permissions",
        phi_detected=False,
    )
    entry1 = service.record_audit_event(req1)
    assert entry1.sequence_index == 0
    assert entry1.prev_hash == "0" * 64
    assert len(entry1.current_hash) == 64

    # 2. Record second event
    req2 = RecordAuditEventRequestDTO(
        event_type="tool_execution",
        agent_id="agent-nurse-bot",
        session_id="encounter-session-001",
        action_summary="Queried EHR laboratory findings",
        phi_detected=True,
    )
    entry2 = service.record_audit_event(req2)
    assert entry2.sequence_index == 1
    assert entry2.prev_hash == entry1.current_hash

    # 3. Verify integrity
    verify_res = service.verify_audit_chain()
    assert verify_res.is_valid is True
    assert "integrity" in verify_res.detail.lower()


def test_export_compliance_package(service: EnterpriseHipaaComplianceService) -> None:
    # Append event
    service.record_audit_event(
        RecordAuditEventRequestDTO(
            event_type="policy_check",
            agent_id="system-gate",
            session_id="audit-sess-5",
            action_summary="Validated HIPAA egress gate",
        )
    )

    pkg_req = ExportCompliancePackageRequestDTO(compliance_standard="hipaa")
    pkg = service.export_compliance_package(pkg_req)

    assert pkg.export_id.startswith("exp-")
    assert pkg.compliance_standard == "hipaa"
    assert pkg.chain_valid is True
    assert pkg.total_events >= 1
    assert len(pkg.summary_digest) == 64
    assert len(pkg.ledger_entries) == pkg.total_events


def test_phi_screening(service: EnterpriseHipaaComplianceService) -> None:
    # Clean text
    clean_res = service.screen_phi(
        PhiScreeningRequestDTO(content="Patient is resting comfortably in room 204.")
    )
    assert clean_res.is_clean is True
    assert len(clean_res.detected_phi_categories) == 0

    # Text containing PHI (SSN, MRN, NPI)
    phi_text = "Patient SSN is 123-45-6789 and MRN is MRN-987654. Attending NPI is 1234567890."
    phi_res = service.screen_phi(PhiScreeningRequestDTO(content=phi_text))
    assert phi_res.is_clean is False
    assert len(phi_res.detected_phi_categories) >= 2
    assert "123-45-6789" not in phi_res.sanitized_content
    assert "[REDACTED_SSN]" in phi_res.sanitized_content


def test_validate_egress_and_metrics(service: EnterpriseHipaaComplianceService) -> None:
    # 1. Valid BAA signed provider
    val_valid = service.validate_egress(
        ValidateProviderEgressRequestDTO(
            provider_id="azure-openai-enterprise-eastus",
            content="Summary note without PHI",
        )
    )
    assert val_valid.allowed is True
    assert val_valid.headers.get("X-Data-Sovereignty") == "hipaa-strict"
    assert val_valid.headers.get("X-Opt-Out-Training") == "true"

    # 2. Unknown provider
    val_unknown = service.validate_egress(
        ValidateProviderEgressRequestDTO(
            provider_id="unknown-public-model",
            content="EHR note",
        )
    )
    assert val_unknown.allowed is False
    assert "not in the approved" in val_unknown.diagnostic.lower()

    # 3. Check operational metrics
    metrics = service.get_metrics()
    assert metrics.providers_registered_total >= 2
    assert metrics.zero_training_headers_injected_total >= 1
    assert metrics.unverified_egress_denied_total >= 1
