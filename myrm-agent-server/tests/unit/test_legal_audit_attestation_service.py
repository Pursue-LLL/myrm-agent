"""
[POS] tests/unit/test_legal_audit_attestation_service.py
[INPUT] app.schemas.legal_audit_attestation, app.services.security.legal_audit_attestation_service
[OUTPUT] unit tests

Tests for LegalAuditAttestationService logic.
Strict typing applied: No `Any` types allowed.
"""

from app.schemas.legal_audit_attestation import (
    AuditEntryCreateRequest,
    DigestAlgorithmEnum,
    EvidenceDossierPackRequest,
    EvidenceDossierVerifyRequest,
    TsaAnchorRequest,
    VerificationStatusEnum,
)
from app.services.security.legal_audit_attestation_service import (
    LegalAuditAttestationService,
)


def _make_sample_request(action: str = "sign_corporate_contract") -> AuditEntryCreateRequest:
    return AuditEntryCreateRequest(
        session_id="session-audit-100",
        actor_id="user-cfo-alice",
        agent_cert_id="cert-myrm-finance-001",
        action_name=action,
        input_payload={"contract_id": "CT-2026-999", "amount": "1200000"},
        output_payload={"status": "executed", "signature": "sig-hex-777"},
        metadata={"network_ip": "192.168.1.100", "region": "bj"},
    )


def test_service_record_entry_and_ledger_status() -> None:
    service = LegalAuditAttestationService()
    initial_status = service.get_ledger_status()
    assert initial_status.total_entries == 0

    req = _make_sample_request()
    node = service.record_entry(req)
    assert node.leaf_index == 0
    assert len(node.leaf_hash) == 64

    status = service.get_ledger_status()
    assert status.total_entries == 1
    assert status.root_hash == node.leaf_hash


def test_service_anchor_tsa() -> None:
    service = LegalAuditAttestationService()
    service.record_entry(_make_sample_request())

    anchor_req = TsaAnchorRequest(algorithm=DigestAlgorithmEnum.SHA256)
    token = service.anchor_tsa(anchor_req)

    assert token.authority_id == "CN-GUIZHOU-CA-TSA-01"
    assert len(token.digest) == 64
    assert len(token.signature_hex) == 64

    # Check metrics
    metrics = service.get_metrics()
    assert metrics.total_tsa_tokens_issued >= 1


def test_service_pack_and_verify_dossier() -> None:
    service = LegalAuditAttestationService()
    node = service.record_entry(_make_sample_request())

    # Pack dossier
    pack_req = EvidenceDossierPackRequest(
        entry_id=node.entry_id,
        approver_id="approver-legal-counsel",
        metadata={"case_ref": "DISPUTE-001"},
    )
    dossier = service.pack_dossier(pack_req)
    assert dossier is not None
    assert dossier.approver_id == "approver-legal-counsel"
    assert dossier.entry_id == node.entry_id

    # Verify dossier
    verify_req = EvidenceDossierVerifyRequest(dossier=dossier)
    verdict = service.verify_dossier(verify_req)

    assert verdict.is_valid is True
    assert verdict.status == VerificationStatusEnum.VALID
    assert verdict.leaf_match is True
    assert verdict.root_match is True
    assert verdict.tsa_match is True
    assert verdict.signature_match is True


def test_service_pack_nonexistent_entry_returns_none() -> None:
    service = LegalAuditAttestationService()
    pack_req = EvidenceDossierPackRequest(entry_id="nonexistent-entry-id")
    dossier = service.pack_dossier(pack_req)
    assert dossier is None
