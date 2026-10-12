"""
[POS] tests/unit/test_ephemeral_identity_voucher_service.py
[INPUT] app.schemas.ephemeral_identity_voucher, app.services.security.ephemeral_identity_voucher_service
[OUTPUT] Unit tests for EphemeralIdentityVoucherService

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from app.schemas.ephemeral_identity_voucher import (
    IssueIdentityRequestDTO,
    IssueVoucherRequestDTO,
    RecordAuditPhaseRequestDTO,
    RedeemVoucherRequestDTO,
    RevokeIdentityRequestDTO,
    VerifyIdentityRequestDTO,
    VoidVoucherRequestDTO,
)
from app.services.security.ephemeral_identity_voucher_service import (
    EphemeralIdentityVoucherService,
)


def test_service_identity_lifecycle() -> None:
    """Test identity issuance, validation, revocation, and consumption."""
    service = EphemeralIdentityVoucherService()

    # 1. Issue
    issue_req = IssueIdentityRequestDTO(
        agent_id="agent-checkout-007",
        task_id="task-shop-5512",
        allowed_scopes=["order.create", "payment.authorize"],
        ttl_seconds=500.0,
        metadata={"channel": "mobile-web"},
    )
    identity = service.issue_identity(issue_req)
    assert identity.identity_id.startswith("eph-id-")
    assert identity.status == "ACTIVE"
    assert "payment.authorize" in identity.allowed_scopes

    # 2. Get
    fetched = service.get_identity(identity.identity_id)
    assert fetched is not None
    assert fetched.agent_id == "agent-checkout-007"

    # 3. Verify valid
    verify_res = service.verify_identity(
        VerifyIdentityRequestDTO(
            identity_id=identity.identity_id,
            ephemeral_token=identity.ephemeral_token,
            required_scope="payment.authorize",
        )
    )
    assert verify_res.is_valid is True
    assert verify_res.status == "ACTIVE"

    # 4. Verify unauthorized scope
    verify_unauth = service.verify_identity(
        VerifyIdentityRequestDTO(
            identity_id=identity.identity_id,
            ephemeral_token=identity.ephemeral_token,
            required_scope="admin.superkey",
        )
    )
    assert verify_unauth.is_valid is False

    # 5. Revoke
    revoked = service.revoke_identity(
        identity.identity_id,
        RevokeIdentityRequestDTO(reason="Security check failed"),
    )
    assert revoked is True

    # 6. Verify after revocation
    verify_revoked = service.verify_identity(
        VerifyIdentityRequestDTO(
            identity_id=identity.identity_id,
            ephemeral_token=identity.ephemeral_token,
        )
    )
    assert verify_revoked.is_valid is False
    assert verify_revoked.status == "REVOKED"


def test_service_single_use_consume() -> None:
    """Test consuming an active identity for single-use self-destruction."""
    service = EphemeralIdentityVoucherService()
    identity = service.issue_identity(
        IssueIdentityRequestDTO(
            agent_id="agent-single-use",
            task_id="task-su-1",
            allowed_scopes=["api.call"],
        )
    )
    assert identity.status == "ACTIVE"

    consumed = service.consume_identity(identity.identity_id)
    assert consumed is True

    # Check state after consume
    fetched = service.get_identity(identity.identity_id)
    assert fetched is not None
    assert fetched.status == "CONSUMED"


def test_service_voucher_domain_and_cap_enforcement() -> None:
    """Test payment voucher domain mismatch and monetary cap enforcement."""
    service = EphemeralIdentityVoucherService()

    # 1. Issue voucher
    voucher = service.issue_voucher(
        IssueVoucherRequestDTO(
            identity_id="eph-id-01",
            target_merchant_domain="https://api.github.com/marketplace",
            max_authorized_amount=100.0,
            currency="USD",
            ttl_seconds=600.0,
        )
    )
    assert voucher.target_merchant_domain == "api.github.com"
    assert voucher.status == "ISSUED"

    # 2. Get voucher
    fetched_v = service.get_voucher(voucher.voucher_id)
    assert fetched_v is not None
    assert fetched_v.max_authorized_amount == 100.0

    # 3. Domain mismatch rejection
    res_mismatch = service.redeem_voucher(
        RedeemVoucherRequestDTO(
            voucher_id=voucher.voucher_id,
            single_use_token=voucher.single_use_token,
            request_domain="evil-phishing.com",
            requested_amount=25.0,
        )
    )
    assert res_mismatch.is_success is False
    assert res_mismatch.status == "DOMAIN_MISMATCH"

    # 4. Monetary limit breach rejection on a fresh voucher
    voucher_cap = service.issue_voucher(
        IssueVoucherRequestDTO(
            identity_id="eph-id-02",
            target_merchant_domain="api.github.com",
            max_authorized_amount=50.0,
            currency="USD",
        )
    )
    res_cap = service.redeem_voucher(
        RedeemVoucherRequestDTO(
            voucher_id=voucher_cap.voucher_id,
            single_use_token=voucher_cap.single_use_token,
            request_domain="api.github.com",
            requested_amount=75.0,
        )
    )
    assert res_cap.is_success is False
    assert res_cap.status == "LIMIT_EXCEEDED"

    # 5. Successful redemption
    voucher_valid = service.issue_voucher(
        IssueVoucherRequestDTO(
            identity_id="eph-id-03",
            target_merchant_domain="api.github.com",
            max_authorized_amount=50.0,
            currency="USD",
        )
    )
    res_success = service.redeem_voucher(
        RedeemVoucherRequestDTO(
            voucher_id=voucher_valid.voucher_id,
            single_use_token=voucher_valid.single_use_token,
            request_domain="api.github.com",
            requested_amount=49.99,
            merchant_order_ref="GH-SUB-2026",
        )
    )
    assert res_success.is_success is True
    assert res_success.status == "REDEEMED"
    assert res_success.voucher is not None
    assert res_success.voucher.redeemed_amount == 49.99

    # 6. Void voucher
    voucher_to_void = service.issue_voucher(
        IssueVoucherRequestDTO(
            identity_id="eph-id-04",
            target_merchant_domain="api.github.com",
            max_authorized_amount=20.0,
        )
    )
    voided = service.void_voucher(
        voucher_to_void.voucher_id, VoidVoucherRequestDTO(reason="Cancelled by user")
    )
    assert voided is True
    fetched_voided = service.get_voucher(voucher_to_void.voucher_id)
    assert fetched_voided is not None
    assert fetched_voided.status == "VOIDED"


def test_service_merkle_audit_trail_and_bundle_export() -> None:
    """Test four-phase audit logging and cryptographic proof bundle export."""
    service = EphemeralIdentityVoucherService()
    task_id = "task-flight-purchase-88"

    # Record 4 phases
    service.record_audit_phase(
        RecordAuditPhaseRequestDTO(
            task_id=task_id,
            phase="USER_INTENT",
            summary="User clicked approve purchase",
            structured_payload={"user_id": "usr-1", "action": "buy_ticket"},
        )
    )
    service.record_audit_phase(
        RecordAuditPhaseRequestDTO(
            task_id=task_id,
            phase="CREDENTIAL_GRANT",
            summary="Ephemeral voucher issued",
            structured_payload={"voucher_id": "vch-123"},
        )
    )
    service.record_audit_phase(
        RecordAuditPhaseRequestDTO(
            task_id=task_id,
            phase="EXECUTION_SNAPSHOT",
            summary="Checkout submitted in sandbox",
            structured_payload={"status": "submitted"},
        )
    )
    service.record_audit_phase(
        RecordAuditPhaseRequestDTO(
            task_id=task_id,
            phase="SETTLEMENT_RECEIPT",
            summary="Order confirmed",
            structured_payload={"order_id": "ORD-9912"},
        )
    )

    # Verify audit trail
    verification = service.verify_audit_trail(task_id)
    assert verification.is_valid is True
    assert verification.merkle_root is not None

    # Export bundle
    bundle = service.export_proof_bundle(task_id)
    assert bundle.task_id == task_id
    assert bundle.verification_success is True
    assert len(bundle.events) == 4
    assert len(bundle.phases_included) == 4

    # Metrics
    metrics = service.get_metrics()
    assert metrics.audit_events_recorded_total == 4
