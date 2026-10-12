"""
[POS] tests/unit/test_air_gapped_sovereignty_service.py
[INPUT] app.services.security.air_gapped_sovereignty_service, app.schemas.air_gapped_sovereignty
[OUTPUT] Unit tests for AirGappedSovereigntyService

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import time

from app.schemas.air_gapped_sovereignty import (
    AuditBundlePackRequest,
    AuditBundleVerifyRequest,
    ImportCrlRequest,
    ModelResolutionRequest,
    ModeUpdateRequest,
    NetworkConnectivityModeEnum,
    OfflineCertValidationRequest,
    SovereignCryptoHashRequest,
)
from app.services.security.air_gapped_sovereignty_service import AirGappedSovereigntyService


def test_service_mode_switch() -> None:
    """Test switching network operational modes."""
    service = AirGappedSovereigntyService()
    init_mode = service.get_network_mode()
    assert init_mode.active_mode == NetworkConnectivityModeEnum.AIR_GAPPED_ISOLATED

    resp = service.set_network_mode(ModeUpdateRequest(mode=NetworkConnectivityModeEnum.ONLINE))
    assert resp.active_mode == NetworkConnectivityModeEnum.ONLINE
    assert service.get_network_mode().active_mode == NetworkConnectivityModeEnum.ONLINE


def test_service_validate_offline_certificate_and_crl() -> None:
    """Test offline certificate validation and CRL revocation list checks."""
    service = AirGappedSovereigntyService()
    now = time.time()

    val_resp = service.validate_offline_certificate(
        OfflineCertValidationRequest(
            cert_pem="CERT-PROD-SVC-01",
            cert_serial="SN-SVC-100",
            issuer_ca="GuizhouCA",
            valid_until=now + 86400,
        )
    )
    assert val_resp.is_valid is True
    assert val_resp.is_revoked is False
    assert val_resp.ca_name == "GuizhouCA"
    assert val_resp.fingerprint_sm3 is not None

    # Import CRL
    crl_res = service.import_crl(ImportCrlRequest(revoked_serials=["SN-SVC-100"]))
    assert crl_res.imported_count == 1

    # Re-validate revoked certificate
    rev_resp = service.validate_offline_certificate(
        OfflineCertValidationRequest(
            cert_pem="CERT-PROD-SVC-01",
            cert_serial="SN-SVC-100",
            issuer_ca="GuizhouCA",
            valid_until=now + 86400,
        )
    )
    assert rev_resp.is_valid is False
    assert rev_resp.is_revoked is True


def test_service_resolve_model_fallback() -> None:
    """Test sovereign local model routing and fallback behavior."""
    service = AirGappedSovereigntyService()
    # Default is AIR_GAPPED_ISOLATED
    res = service.resolve_model(
        ModelResolutionRequest(requested_model_id="gpt-4o", is_remote_healthy=True)
    )
    assert res.was_fallback is True
    assert res.effective_target.is_local_sovereign is True
    assert res.effective_target.model_id == "qwen2.5-coder:32b"


def test_service_pack_and_verify_audit_bundle() -> None:
    """Test sealing evidentiary records and verifying against bundle digest."""
    service = AirGappedSovereigntyService()
    records = [
        {"timestamp": "1775510001", "event": "ISOLATION_VERIFIED"},
        {"timestamp": "1775510002", "event": "MODEL_LOCAL_INFERENCE_DONE"},
    ]

    bundle = service.pack_audit_bundle(
        AuditBundlePackRequest(records=records, metadata={"agent": "agent-01"})
    )
    assert bundle.record_count == 2
    assert bundle.is_sealed is True

    # Valid verification
    ver_valid = service.verify_audit_bundle(
        AuditBundleVerifyRequest(bundle=bundle, raw_records=records)
    )
    assert ver_valid.is_valid is True

    # Tampered verification
    tampered = [records[0], {"timestamp": "1775510002", "event": "TAMPERED_LOG"}]
    ver_tampered = service.verify_audit_bundle(
        AuditBundleVerifyRequest(bundle=bundle, raw_records=tampered)
    )
    assert ver_tampered.is_valid is False


def test_service_sm3_hash_and_metrics() -> None:
    """Test SM3 hashing calculation and cumulative metrics retrieval."""
    service = AirGappedSovereigntyService()
    hash_resp = service.compute_sm3_hash(SovereignCryptoHashRequest(data="abc"))
    assert (
        hash_resp.sm3_digest
        == "66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0"
    )

    metrics = service.get_metrics()
    assert metrics.total_offline_validations >= 0
    assert metrics.audit_bundles_sealed >= 0
