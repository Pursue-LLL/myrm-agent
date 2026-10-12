"""Unit test for ZeroEgressProvenanceService.

[INPUT]
- RecordAuditEventRequest, GenerateZeroEgressCertificateRequest, CreateAssetProvenanceRequest, VerifyAssetProvenanceRequest.

[OUTPUT]
- Verified behavior of ZeroEgressProvenanceService methods.

[POS]
- Server unit test layer.
"""

from __future__ import annotations

from app.schemas.zero_egress_provenance import (
    CreateAssetProvenanceRequest,
    GenerateZeroEgressCertificateRequest,
    RecordAuditEventRequest,
    VerifyAssetProvenanceRequest,
)
from app.services.security.zero_egress_provenance_service import (
    ZeroEgressProvenanceService,
)


def test_service_audit_ledger_operations() -> None:
    service = ZeroEgressProvenanceService()

    # 1. Record event
    rec = service.record_event(
        RecordAuditEventRequest(
            actor="agent-planner",
            action_type="SANDBOX_EXECUTE",
            resource_target="/workspace/run.sh",
            input_payload="bash run.sh",
            output_payload="completed with exit 0",
            boundary_state="SANDBOX_CONFINED",
        )
    )
    assert rec.sequence_number == 0
    assert rec.boundary_state == "SANDBOX_CONFINED"
    assert len(rec.current_record_hash) == 64

    # 2. Verify ledger
    verify_res = service.verify_ledger()
    assert verify_res.is_intact is True
    assert verify_res.total_records >= 1

    # 3. Export ledger
    records = service.export_ledger()
    assert len(records) >= 1
    assert any(r.record_id == rec.record_id for r in records)


def test_service_certificate_and_provenance_flow() -> None:
    service = ZeroEgressProvenanceService()

    # 1. Generate zero-egress certificate
    cert = service.generate_certificate(
        GenerateZeroEgressCertificateRequest(
            session_id="session-alpha",
            tenant_id="tenant-acme",
            sandbox_id="sbx-confined",
            attestation_level="ENTERPRISE_ZERO_EGRESS",
        )
    )
    assert cert.zero_data_retention_guaranteed is True
    assert cert.no_model_training_guaranteed is True
    assert cert.session_id == "session-alpha"

    # 2. Create asset provenance dossier
    code = "def secure_add(a: int, b: int) -> int: return a + b"
    dossier = service.create_provenance(
        CreateAssetProvenanceRequest(
            asset_id="asset-math",
            asset_name="math.py",
            media_type="text/x-python",
            content=code,
            session_id="session-alpha",
            prompt_text="Write a secure add function.",
            foundation_model_id="claude-3-7-sonnet",
            ip_tier="ENTERPRISE_INDEMNIFIED",
        )
    )
    assert dossier.asset_id == "asset-math"
    assert dossier.ip_tier == "ENTERPRISE_INDEMNIFIED"

    # 3. Verify provenance match
    v_match = service.verify_provenance(
        VerifyAssetProvenanceRequest(dossier=dossier, content=code)
    )
    assert v_match.is_verified is True

    # 4. Verify provenance mismatch
    v_mismatch = service.verify_provenance(
        VerifyAssetProvenanceRequest(dossier=dossier, content=code + "\n# tampered")
    )
    assert v_mismatch.is_verified is False
