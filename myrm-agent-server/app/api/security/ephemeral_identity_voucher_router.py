"""
[POS] app/api/security/ephemeral_identity_voucher_router.py
[INPUT] fastapi, app.schemas.ephemeral_identity_voucher, app.services.security.ephemeral_identity_voucher_service
[OUTPUT] ephemeral_identity_voucher_router

REST API router for Dynamic Ephemeral Identity & Verifiable Audit Trail Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

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
from app.services.security.ephemeral_identity_voucher_service import (
    EphemeralIdentityVoucherService,
    get_ephemeral_identity_voucher_service,
)

router = APIRouter(
    prefix="/ephemeral-identity-voucher",
    tags=["Ephemeral Identity & Verifiable Audit"],
)


@router.post(
    "/identities",
    response_model=EphemeralIdentityResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Issue ephemeral sub-identity",
)
def issue_identity(
    request: IssueIdentityRequestDTO,
    service: EphemeralIdentityVoucherService = Depends(
        get_ephemeral_identity_voucher_service
    ),
) -> EphemeralIdentityResponseDTO:
    """Issue a short-lived micro-scoped identity credential."""
    return service.issue_identity(request)


@router.post(
    "/identities/verify",
    response_model=VerifyIdentityResponseDTO,
    summary="Verify ephemeral identity token",
)
def verify_identity(
    request: VerifyIdentityRequestDTO,
    service: EphemeralIdentityVoucherService = Depends(
        get_ephemeral_identity_voucher_service
    ),
) -> VerifyIdentityResponseDTO:
    """Verify validity, expiration, and authorized scope of an ephemeral identity token."""
    return service.verify_identity(request)


@router.post(
    "/identities/{identity_id}/revoke",
    response_model=dict[str, bool],
    summary="Revoke ephemeral identity",
)
def revoke_identity(
    identity_id: str,
    request: RevokeIdentityRequestDTO,
    service: EphemeralIdentityVoucherService = Depends(
        get_ephemeral_identity_voucher_service
    ),
) -> dict[str, bool]:
    """Revoke an active identity credential immediately."""
    revoked = service.revoke_identity(identity_id, request)
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Identity {identity_id} not found or already revoked",
        )
    return {"revoked": True}


@router.post(
    "/identities/{identity_id}/consume",
    response_model=dict[str, bool],
    summary="Consume single-use ephemeral identity",
)
def consume_identity(
    identity_id: str,
    service: EphemeralIdentityVoucherService = Depends(
        get_ephemeral_identity_voucher_service
    ),
) -> dict[str, bool]:
    """Mark an ephemeral identity as consumed (single-use destruction)."""
    consumed = service.consume_identity(identity_id)
    if not consumed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Identity {identity_id} not found or not active",
        )
    return {"consumed": True}


@router.get(
    "/identities/{identity_id}",
    response_model=EphemeralIdentityResponseDTO,
    summary="Get ephemeral identity details",
)
def get_identity(
    identity_id: str,
    service: EphemeralIdentityVoucherService = Depends(
        get_ephemeral_identity_voucher_service
    ),
) -> EphemeralIdentityResponseDTO:
    """Retrieve identity record by identity ID."""
    identity = service.get_identity(identity_id)
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Identity {identity_id} not found",
        )
    return identity


@router.post(
    "/vouchers",
    response_model=MerchantLockedVoucherResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Issue merchant-locked disposable voucher",
)
def issue_voucher(
    request: IssueVoucherRequestDTO,
    service: EphemeralIdentityVoucherService = Depends(
        get_ephemeral_identity_voucher_service
    ),
) -> MerchantLockedVoucherResponseDTO:
    """Generate a single-use payment voucher strictly bound to a merchant domain."""
    return service.issue_voucher(request)


@router.post(
    "/vouchers/redeem",
    response_model=RedeemVoucherResponseDTO,
    summary="Redeem merchant-locked payment voucher",
)
def redeem_voucher(
    request: RedeemVoucherRequestDTO,
    service: EphemeralIdentityVoucherService = Depends(
        get_ephemeral_identity_voucher_service
    ),
) -> RedeemVoucherResponseDTO:
    """Redeem a disposable payment voucher with domain and cap enforcement."""
    return service.redeem_voucher(request)


@router.post(
    "/vouchers/{voucher_id}/void",
    response_model=dict[str, bool],
    summary="Void an unredeemed voucher",
)
def void_voucher(
    voucher_id: str,
    request: VoidVoucherRequestDTO,
    service: EphemeralIdentityVoucherService = Depends(
        get_ephemeral_identity_voucher_service
    ),
) -> dict[str, bool]:
    """Void an unspent payment voucher."""
    voided = service.void_voucher(voucher_id, request)
    if not voided:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Voucher {voucher_id} not found or not in ISSUED state",
        )
    return {"voided": True}


@router.get(
    "/vouchers/{voucher_id}",
    response_model=MerchantLockedVoucherResponseDTO,
    summary="Get voucher details",
)
def get_voucher(
    voucher_id: str,
    service: EphemeralIdentityVoucherService = Depends(
        get_ephemeral_identity_voucher_service
    ),
) -> MerchantLockedVoucherResponseDTO:
    """Retrieve payment voucher details by voucher ID."""
    voucher = service.get_voucher(voucher_id)
    if voucher is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Voucher {voucher_id} not found",
        )
    return voucher


@router.post(
    "/audit/events",
    response_model=AuditEventResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Record audit phase event",
)
def record_audit_phase(
    request: RecordAuditPhaseRequestDTO,
    service: EphemeralIdentityVoucherService = Depends(
        get_ephemeral_identity_voucher_service
    ),
) -> AuditEventResponseDTO:
    """Append cryptographically chained phase event to Merkle audit ledger."""
    return service.record_audit_phase(request)


@router.get(
    "/audit/verify/{task_id}",
    response_model=VerifyAuditTrailResponseDTO,
    summary="Verify task audit trail integrity",
)
def verify_audit_trail(
    task_id: str,
    service: EphemeralIdentityVoucherService = Depends(
        get_ephemeral_identity_voucher_service
    ),
) -> VerifyAuditTrailResponseDTO:
    """Verify unbroken chain of audit events and return computed Merkle root."""
    return service.verify_audit_trail(task_id)


@router.get(
    "/audit/bundle/{task_id}",
    response_model=AuditProofBundleResponseDTO,
    summary="Export verifiable audit proof bundle",
)
def export_proof_bundle(
    task_id: str,
    service: EphemeralIdentityVoucherService = Depends(
        get_ephemeral_identity_voucher_service
    ),
) -> AuditProofBundleResponseDTO:
    """Export complete cryptographic proof bundle with Merkle root."""
    return service.export_proof_bundle(task_id)


@router.get(
    "/metrics",
    response_model=EphemeralIdentityMetricsResponseDTO,
    summary="Get operational metrics",
)
def get_metrics(
    service: EphemeralIdentityVoucherService = Depends(
        get_ephemeral_identity_voucher_service
    ),
) -> EphemeralIdentityMetricsResponseDTO:
    """Retrieve operational metric counters for identities, vouchers, and audit ledger."""
    return service.get_metrics()
