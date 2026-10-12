"""
[POS] app/api/security/confidential_payment_sandbox_router.py
[INPUT] fastapi, app.schemas.confidential_payment_sandbox, app.services.security.confidential_payment_sandbox_service
[OUTPUT] confidential_payment_sandbox_router
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

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
from app.services.security.confidential_payment_sandbox_service import (
    ConfidentialPaymentSandboxService,
    get_confidential_payment_sandbox_service,
)

router = APIRouter(
    prefix="/confidential-payment-sandbox",
    tags=["Confidential VM Enclave & Virtual Card Payment Proxy"],
)


@router.post(
    "/attestation/verify",
    response_model=ConfidentialEnclaveAttestationDTO,
    summary="Verify hardware enclave remote attestation proof",
)
def verify_enclave_attestation(
    request: VerifyEnclaveRequestDTO,
    service: ConfidentialPaymentSandboxService = Depends(
        get_confidential_payment_sandbox_service
    ),
) -> ConfidentialEnclaveAttestationDTO:
    """Verify AMD SEV-SNP / Intel TDX hardware cryptographic remote attestation proof."""
    return service.verify_enclave(request)


@router.post(
    "/cards/issue",
    response_model=SingleUseVirtualCardDTO,
    summary="Issue a disposable blind virtual payment card",
)
def issue_virtual_card(
    request: IssueVirtualCardRequestDTO,
    service: ConfidentialPaymentSandboxService = Depends(
        get_confidential_payment_sandbox_service
    ),
) -> SingleUseVirtualCardDTO:
    """Issue a single-use virtual card token isolated from plain card credentials."""
    return service.issue_virtual_card(request)


@router.get(
    "/cards/{card_token}",
    response_model=SingleUseVirtualCardDTO,
    summary="Get virtual card metadata",
)
def get_virtual_card(
    card_token: str,
    service: ConfidentialPaymentSandboxService = Depends(
        get_confidential_payment_sandbox_service
    ),
) -> SingleUseVirtualCardDTO:
    """Fetch virtual card metadata by opaque token."""
    card = service.get_virtual_card(card_token)
    if not card:
        raise HTTPException(status_code=404, detail="Virtual card not found")
    return card


@router.post(
    "/cards/pay",
    response_model=VirtualCardPaymentReceiptDTO,
    summary="Execute payment with disposable virtual card",
)
def process_virtual_payment(
    request: VirtualCardPaymentRequestDTO,
    service: ConfidentialPaymentSandboxService = Depends(
        get_confidential_payment_sandbox_service
    ),
) -> VirtualCardPaymentReceiptDTO:
    """Settle an e-commerce or booking purchase using a blind virtual card token."""
    return service.process_payment(request)


@router.post(
    "/sentinel/scan-ingress",
    response_model=DualSentinelScanResultDTO,
    summary="Scan ingress stream for prompt injections",
)
def scan_ingress_message(
    request: ScanMessageRequestDTO,
    service: ConfidentialPaymentSandboxService = Depends(
        get_confidential_payment_sandbox_service
    ),
) -> DualSentinelScanResultDTO:
    """Inspect inbound prompt payload for injection attacks."""
    return service.scan_ingress(request)


@router.post(
    "/sentinel/scan-egress",
    response_model=DualSentinelScanResultDTO,
    summary="Scan egress stream for card and secret leaks",
)
def scan_egress_message(
    request: ScanMessageRequestDTO,
    service: ConfidentialPaymentSandboxService = Depends(
        get_confidential_payment_sandbox_service
    ),
) -> DualSentinelScanResultDTO:
    """Inspect outbound message stream for plain credit cards and private keys."""
    return service.scan_egress(request)


@router.post(
    "/channel/check-access",
    response_model=ChannelAccessCheckResponseDTO,
    summary="Check channel access against default read-only barrier",
)
def check_channel_access(
    request: ChannelAccessCheckRequestDTO,
    service: ConfidentialPaymentSandboxService = Depends(
        get_confidential_payment_sandbox_service
    ),
) -> ChannelAccessCheckResponseDTO:
    """Enforce default read-only barrier on external sensitive channels."""
    return service.check_channel_access(request)


@router.get(
    "/metrics",
    response_model=ConfidentialPaymentMetricsDTO,
    summary="Get operational metrics",
)
def get_metrics(
    service: ConfidentialPaymentSandboxService = Depends(
        get_confidential_payment_sandbox_service
    ),
) -> ConfidentialPaymentMetricsDTO:
    """Fetch cumulative operational metrics for confidential VM and payment proxy."""
    return service.get_metrics()
