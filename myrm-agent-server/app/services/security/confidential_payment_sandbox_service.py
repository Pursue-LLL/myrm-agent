"""
[POS] app/services/security/confidential_payment_sandbox_service.py
[INPUT] app.schemas.confidential_payment_sandbox, myrm_agent_harness.core.security.confidential_payment_sandbox
[OUTPUT] ConfidentialPaymentSandboxService, get_confidential_payment_sandbox_service
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.confidential_payment_sandbox import (
    ConfidentialEnclaveAttestation,
    ConfidentialPaymentSandboxFacade,
    DualSentinelScanResult,
    IngressFenceMode,
    SingleUseVirtualCard,
    VirtualCardPaymentReceipt,
    VirtualCardPaymentRequest,
)

from app.schemas.confidential_payment_sandbox import (
    ChannelAccessCheckRequestDTO,
    ChannelAccessCheckResponseDTO,
    ConfidentialEnclaveAttestationDTO,
    ConfidentialPaymentMetricsDTO,
    DualSentinelScanResultDTO,
    IssueVirtualCardRequestDTO,
    ScanMessageRequestDTO,
    SingleUseVirtualCardDTO,
    VerifyEnclaveRequestDTO,
    VirtualCardPaymentReceiptDTO,
    VirtualCardPaymentRequestDTO,
)

logger = logging.getLogger(__name__)


class ConfidentialPaymentSandboxService:
    """Service mediating confidential enclave verification, blind virtual cards, and dual sentinels."""

    def __init__(self, facade: ConfidentialPaymentSandboxFacade | None = None) -> None:
        self._facade = facade or ConfidentialPaymentSandboxFacade()

    @staticmethod
    def _to_card_dto(card: SingleUseVirtualCard) -> SingleUseVirtualCardDTO:
        return SingleUseVirtualCardDTO(
            card_token=card.card_token,
            masked_card_number=card.masked_card_number,
            currency=card.currency,
            spending_limit=card.spending_limit,
            amount_spent=card.amount_spent,
            status=card.status.value,
            created_at=card.created_at,
            expires_at=card.expires_at,
            requires_hitl=card.requires_hitl,
        )

    @staticmethod
    def _to_receipt_dto(r: VirtualCardPaymentReceipt) -> VirtualCardPaymentReceiptDTO:
        return VirtualCardPaymentReceiptDTO(
            receipt_id=r.receipt_id,
            card_token=r.card_token,
            charged_amount=r.charged_amount,
            currency=r.currency,
            is_success=r.is_success,
            status=r.status,
            merchant_name=r.merchant_name,
            requires_hitl_escalation=r.requires_hitl_escalation,
            message=r.message,
        )

    @staticmethod
    def _to_attestation_dto(att: ConfidentialEnclaveAttestation) -> ConfidentialEnclaveAttestationDTO:
        return ConfidentialEnclaveAttestationDTO(
            enclave_id=att.enclave_id,
            platform_type=att.platform_type,
            status=att.status.value,
            measurement_sha256=att.measurement_sha256,
            attested_at=att.attested_at,
            is_memory_encrypted=att.is_memory_encrypted,
            diagnostic=att.diagnostic,
        )

    @staticmethod
    def _to_sentinel_dto(res: DualSentinelScanResult) -> DualSentinelScanResultDTO:
        return DualSentinelScanResultDTO(
            direction=res.direction,
            is_blocked=res.is_blocked,
            detected_threats=list(res.detected_threats),
            sanitized_content=res.sanitized_content,
            diagnostic=res.diagnostic,
        )

    def verify_enclave(self, request: VerifyEnclaveRequestDTO) -> ConfidentialEnclaveAttestationDTO:
        """Verify remote cryptographic hardware attestation."""
        att = self._facade.verify_enclave_attestation(
            enclave_id=request.enclave_id,
            platform_type=request.platform_type,
            measurement_sha256=request.measurement_sha256,
        )
        return self._to_attestation_dto(att)

    def issue_virtual_card(self, request: IssueVirtualCardRequestDTO) -> SingleUseVirtualCardDTO:
        """Issue a blind disposable single-use virtual payment card."""
        card = self._facade.issue_virtual_card(
            spending_limit=request.spending_limit,
            currency=request.currency,
            validity_seconds=request.validity_seconds,
            hitl_threshold=request.hitl_threshold,
        )
        return self._to_card_dto(card)

    def get_virtual_card(self, card_token: str) -> SingleUseVirtualCardDTO | None:
        """Retrieve virtual card metadata by token."""
        card = self._facade.get_virtual_card(card_token)
        return self._to_card_dto(card) if card else None

    def process_payment(self, request: VirtualCardPaymentRequestDTO) -> VirtualCardPaymentReceiptDTO:
        """Settle a payment using a virtual card token."""
        domain_req = VirtualCardPaymentRequest(
            card_token=request.card_token,
            amount=request.amount,
            currency=request.currency,
            merchant_name=request.merchant_name,
            item_description=request.item_description,
            idempotency_key=request.idempotency_key,
        )
        receipt = self._facade.process_virtual_payment(
            request=domain_req, confirmed_by_user=request.confirmed_by_user
        )
        return self._to_receipt_dto(receipt)

    def cancel_virtual_card(self, card_token: str) -> bool:
        """Cancel an unused virtual card."""
        return self._facade.cancel_virtual_card(card_token)

    def scan_ingress(self, request: ScanMessageRequestDTO) -> DualSentinelScanResultDTO:
        """Scan inbound message for prompt injection."""
        res = self._facade.scan_ingress_message(request.content)
        return self._to_sentinel_dto(res)

    def scan_egress(self, request: ScanMessageRequestDTO) -> DualSentinelScanResultDTO:
        """Scan outbound message for credential or credit card leaks."""
        res = self._facade.scan_egress_message(request.content)
        return self._to_sentinel_dto(res)

    def check_channel_access(self, request: ChannelAccessCheckRequestDTO) -> ChannelAccessCheckResponseDTO:
        """Enforce default read-only fence on external channel."""
        fence_mode = (
            IngressFenceMode.ELEVATED_WRITE_PERMITTED
            if request.fence_mode == "elevated_write_permitted"
            else IngressFenceMode.READ_ONLY
        )
        allowed, reason = self._facade.check_external_channel_access(
            channel_name=request.channel_name,
            action_type=request.action_type,
            fence_mode=fence_mode,
        )
        return ChannelAccessCheckResponseDTO(allowed=allowed, reason=reason)

    def get_metrics(self) -> ConfidentialPaymentMetricsDTO:
        """Fetch cumulative operational metrics."""
        m = self._facade.metrics
        return ConfidentialPaymentMetricsDTO(
            attestations_verified_total=m.attestations_verified_total,
            cards_issued_total=m.cards_issued_total,
            payments_processed_total=m.payments_processed_total,
            hitl_escalations_total=m.hitl_escalations_total,
            ingress_injections_blocked_total=m.ingress_injections_blocked_total,
            egress_leaks_prevented_total=m.egress_leaks_prevented_total,
        )


_global_service: ConfidentialPaymentSandboxService | None = None


def get_confidential_payment_sandbox_service() -> ConfidentialPaymentSandboxService:
    """Singleton provider for ConfidentialPaymentSandboxService."""
    global _global_service
    if _global_service is None:
        _global_service = ConfidentialPaymentSandboxService()
    return _global_service
