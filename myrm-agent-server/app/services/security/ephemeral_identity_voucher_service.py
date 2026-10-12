"""
[POS] app/services/security/ephemeral_identity_voucher_service.py
[INPUT] app.schemas.ephemeral_identity_voucher, myrm_agent_harness.core.security.ephemeral_identity_voucher
[OUTPUT] EphemeralIdentityVoucherService, get_ephemeral_identity_voucher_service

Service layer for Dynamic Ephemeral Identity & Verifiable Audit Trail Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.ephemeral_identity_voucher import (
    AuditEventRecord,
    AuditPhase,
    AuditProofBundle,
    EphemeralIdentity,
    EphemeralIdentityAndVoucherFacade,
    MerchantLockedVoucher,
)

from app.schemas.ephemeral_identity_voucher import (
    AuditEventResponseDTO,
    AuditProofBundleResponseDTO,
    EphemeralIdentityMetricsResponseDTO,
    EphemeralIdentityResponseDTO,
    IssueIdentityRequestDTO,
    IssueVoucherRequestDTO,
    MerchantLockedVoucherResponseDTO,
    RecordAuditPhaseRequestDTO,
    RedeemVoucherRequestDTO,
    RedeemVoucherResponseDTO,
    RevokeIdentityRequestDTO,
    VerifyAuditTrailResponseDTO,
    VerifyIdentityRequestDTO,
    VerifyIdentityResponseDTO,
    VoidVoucherRequestDTO,
)

logger = logging.getLogger(__name__)


class EphemeralIdentityVoucherService:
    """Orchestrates short-lived micro-scoped credentials, payment vouchers, and Merkle audit ledgers."""

    def __init__(self, facade: EphemeralIdentityAndVoucherFacade | None = None) -> None:
        self._facade = facade or EphemeralIdentityAndVoucherFacade()

    def issue_identity(
        self, request: IssueIdentityRequestDTO
    ) -> EphemeralIdentityResponseDTO:
        """Provision a fresh ephemeral identity for an autonomous sub-task."""
        identity = self._facade.issue_ephemeral_identity(
            agent_id=request.agent_id,
            task_id=request.task_id,
            allowed_scopes=tuple(request.allowed_scopes),
            ttl_seconds=request.ttl_seconds,
            metadata=request.metadata,
        )
        return self._map_identity(identity)

    def verify_identity(
        self, request: VerifyIdentityRequestDTO
    ) -> VerifyIdentityResponseDTO:
        """Validate bearer token authenticity, scope permissions, and expiration."""
        is_valid, status, reason = self._facade.verify_ephemeral_identity(
            identity_id=request.identity_id,
            token=request.ephemeral_token,
            required_scope=request.required_scope,
        )
        return VerifyIdentityResponseDTO(
            is_valid=is_valid,
            status=status.value,
            diagnostic_reason=reason,
        )

    def revoke_identity(
        self, identity_id: str, request: RevokeIdentityRequestDTO
    ) -> bool:
        """Revoke active identity immediately."""
        return self._facade.revoke_ephemeral_identity(
            identity_id=identity_id, reason=request.reason
        )

    def consume_identity(self, identity_id: str) -> bool:
        """Mark single-use identity as consumed."""
        return self._facade.consume_identity(identity_id=identity_id)

    def get_identity(self, identity_id: str) -> EphemeralIdentityResponseDTO | None:
        """Retrieve stored identity details."""
        identity = self._facade.get_identity(identity_id=identity_id)
        if identity is None:
            return None
        return self._map_identity(identity)

    def issue_voucher(
        self, request: IssueVoucherRequestDTO
    ) -> MerchantLockedVoucherResponseDTO:
        """Issue domain-locked payment voucher with authorized spending ceiling."""
        voucher = self._facade.issue_merchant_voucher(
            identity_id=request.identity_id,
            target_merchant_domain=request.target_merchant_domain,
            max_authorized_amount=request.max_authorized_amount,
            currency=request.currency,
            ttl_seconds=request.ttl_seconds,
        )
        return self._map_voucher(voucher)

    def redeem_voucher(
        self, request: RedeemVoucherRequestDTO
    ) -> RedeemVoucherResponseDTO:
        """Validate domain match and monetary cap then redeem voucher."""
        success, status, reason, updated_v = self._facade.redeem_merchant_voucher(
            voucher_id=request.voucher_id,
            single_use_token=request.single_use_token,
            request_domain=request.request_domain,
            requested_amount=request.requested_amount,
            order_ref=request.merchant_order_ref,
        )
        mapped_v = self._map_voucher(updated_v) if updated_v is not None else None
        return RedeemVoucherResponseDTO(
            is_success=success,
            status=status.value,
            diagnostic_reason=reason,
            voucher=mapped_v,
        )

    def void_voucher(self, voucher_id: str, request: VoidVoucherRequestDTO) -> bool:
        """Void an unredeemed voucher."""
        return self._facade.void_merchant_voucher(
            voucher_id=voucher_id, reason=request.reason
        )

    def get_voucher(
        self, voucher_id: str
    ) -> MerchantLockedVoucherResponseDTO | None:
        """Retrieve voucher details."""
        voucher = self._facade.get_voucher(voucher_id=voucher_id)
        if voucher is None:
            return None
        return self._map_voucher(voucher)

    def record_audit_phase(
        self, request: RecordAuditPhaseRequestDTO
    ) -> AuditEventResponseDTO:
        """Append cryptographically chained phase event to Merkle audit ledger."""
        phase_enum = self._parse_phase(request.phase)
        record = self._facade.record_audit_phase(
            task_id=request.task_id,
            phase=phase_enum,
            summary=request.summary,
            structured_payload=request.structured_payload,
        )
        return self._map_audit_event(record)

    def verify_audit_trail(self, task_id: str) -> VerifyAuditTrailResponseDTO:
        """Verify unbroken chain and compute Merkle root."""
        is_valid, reason, merkle_root = self._facade.verify_audit_trail(task_id=task_id)
        return VerifyAuditTrailResponseDTO(
            task_id=task_id,
            is_valid=is_valid,
            diagnostic_reason=reason,
            merkle_root=merkle_root,
        )

    def export_proof_bundle(self, task_id: str) -> AuditProofBundleResponseDTO:
        """Export verifiable cryptographic proof bundle."""
        bundle: AuditProofBundle = self._facade.export_proof_bundle(task_id=task_id)
        return AuditProofBundleResponseDTO(
            task_id=bundle.task_id,
            merkle_root=bundle.merkle_root,
            phases_included=list(bundle.phases_included),
            events=[self._map_audit_event(ev) for ev in bundle.events],
            verification_success=bundle.verification_success,
            exported_at_epoch=bundle.exported_at_epoch,
        )

    def get_metrics(self) -> EphemeralIdentityMetricsResponseDTO:
        """Retrieve operational metric counters."""
        m = self._facade.metrics
        return EphemeralIdentityMetricsResponseDTO(
            identities_issued_total=m.identities_issued_total,
            identities_revoked_total=m.identities_revoked_total,
            identities_expired_total=m.identities_expired_total,
            vouchers_issued_total=m.vouchers_issued_total,
            vouchers_redeemed_total=m.vouchers_redeemed_total,
            vouchers_rejected_total=m.vouchers_rejected_total,
            audit_events_recorded_total=m.audit_events_recorded_total,
        )

    @staticmethod
    def _parse_phase(phase_str: str) -> AuditPhase:
        """Parse string to AuditPhase enum safely with fallback."""
        normalized = phase_str.strip().upper()
        for p in AuditPhase:
            if p.value == normalized or p.name == normalized:
                return p
        return AuditPhase.PHASE_1_USER_INTENT

    @staticmethod
    def _map_identity(identity: EphemeralIdentity) -> EphemeralIdentityResponseDTO:
        return EphemeralIdentityResponseDTO(
            identity_id=identity.identity_id,
            agent_id=identity.agent_id,
            task_id=identity.task_id,
            allowed_scopes=list(identity.allowed_scopes),
            ephemeral_token=identity.ephemeral_token,
            created_at_epoch=identity.created_at_epoch,
            expires_at_epoch=identity.expires_at_epoch,
            status=identity.status.value,
            metadata=dict(identity.metadata),
        )

    @staticmethod
    def _map_voucher(voucher: MerchantLockedVoucher) -> MerchantLockedVoucherResponseDTO:
        return MerchantLockedVoucherResponseDTO(
            voucher_id=voucher.voucher_id,
            identity_id=voucher.identity_id,
            target_merchant_domain=voucher.target_merchant_domain,
            max_authorized_amount=voucher.max_authorized_amount,
            currency=voucher.currency,
            single_use_token=voucher.single_use_token,
            created_at_epoch=voucher.created_at_epoch,
            expires_at_epoch=voucher.expires_at_epoch,
            status=voucher.status.value,
            redeemed_amount=voucher.redeemed_amount,
            merchant_order_ref=voucher.merchant_order_ref,
        )

    @staticmethod
    def _map_audit_event(record: AuditEventRecord) -> AuditEventResponseDTO:
        return AuditEventResponseDTO(
            event_id=record.event_id,
            task_id=record.task_id,
            phase=record.phase.value,
            timestamp_epoch=record.timestamp_epoch,
            payload_hash=record.payload_hash,
            raw_summary=record.raw_summary,
            parent_hash=record.parent_hash,
            node_hash=record.node_hash,
        )


_service_instance: EphemeralIdentityVoucherService | None = None


def get_ephemeral_identity_voucher_service() -> EphemeralIdentityVoucherService:
    """Retrieve singleton instance of EphemeralIdentityVoucherService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = EphemeralIdentityVoucherService()
    return _service_instance
