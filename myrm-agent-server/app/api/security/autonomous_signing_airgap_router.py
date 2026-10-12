"""
[POS] app/api/security/autonomous_signing_airgap_router.py
[INPUT] fastapi, app.schemas.autonomous_signing_airgap, app.services.security.autonomous_signing_airgap_service
[OUTPUT] autonomous_signing_airgap_router
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.autonomous_signing_airgap import (
    ApproveStepUpRequestDTO,
    EvaluateSigningRequestDTO,
    KillSwitchStatusResponseDTO,
    QuotaConfigResponseDTO,
    RejectStepUpRequestDTO,
    SigningVerdictResponseDTO,
    TriggerKillSwitchRequestDTO,
    UpdateQuotaConfigRequestDTO,
    WalletAirgapMetricsResponseDTO,
)
from app.services.security.autonomous_signing_airgap_service import (
    AutonomousSigningAirgapService,
    get_autonomous_signing_airgap_service,
)

router = APIRouter(
    prefix="/autonomous-signing-airgap",
    tags=["Autonomous Signing Airgap"],
)


@router.post(
    "/evaluate",
    response_model=SigningVerdictResponseDTO,
    summary="Evaluate and conditionally sign transaction",
)
def evaluate_transaction(
    request: EvaluateSigningRequestDTO,
    service: AutonomousSigningAirgapService = Depends(
        get_autonomous_signing_airgap_service
    ),
) -> SigningVerdictResponseDTO:
    """Evaluate proposed transaction against airgap kill-switch and quota guard, signing if authorized."""
    return service.evaluate_and_sign(request)


@router.post(
    "/step-up/approve",
    response_model=SigningVerdictResponseDTO,
    summary="Approve stepped-up transaction",
)
def approve_step_up_transaction(
    request: ApproveStepUpRequestDTO,
    service: AutonomousSigningAirgapService = Depends(
        get_autonomous_signing_airgap_service
    ),
) -> SigningVerdictResponseDTO:
    """Explicitly approve an escalated transaction following human verification."""
    verdict = service.approve_step_up(request)
    if verdict is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pending transaction '{request.tx_id}' not found for approval",
        )
    return verdict


@router.post(
    "/step-up/reject",
    response_model=dict[str, str | bool],
    summary="Reject stepped-up transaction",
)
def reject_step_up_transaction(
    request: RejectStepUpRequestDTO,
    service: AutonomousSigningAirgapService = Depends(
        get_autonomous_signing_airgap_service
    ),
) -> dict[str, str | bool]:
    """Reject and dismiss a pending escalated transaction."""
    success = service.reject_step_up(request)
    return {"tx_id": request.tx_id, "rejected": success, "reason": request.reason}


@router.get(
    "/step-up/pending",
    response_model=list[EvaluateSigningRequestDTO],
    summary="List transactions pending step-up approval",
)
def list_pending_step_up(
    service: AutonomousSigningAirgapService = Depends(
        get_autonomous_signing_airgap_service
    ),
) -> list[EvaluateSigningRequestDTO]:
    """Retrieve all transactions currently held awaiting human confirmation."""
    return service.list_pending_step_up()


@router.post(
    "/kill-switch/trigger",
    response_model=KillSwitchStatusResponseDTO,
    summary="Trigger emergency wallet freeze",
)
def trigger_kill_switch(
    request: TriggerKillSwitchRequestDTO,
    service: AutonomousSigningAirgapService = Depends(
        get_autonomous_signing_airgap_service
    ),
) -> KillSwitchStatusResponseDTO:
    """Immediately freeze all autonomous signing operations."""
    return service.trigger_kill_switch(request)


@router.post(
    "/kill-switch/release",
    response_model=KillSwitchStatusResponseDTO,
    summary="Release emergency wallet freeze",
)
def release_kill_switch(
    service: AutonomousSigningAirgapService = Depends(
        get_autonomous_signing_airgap_service
    ),
) -> KillSwitchStatusResponseDTO:
    """Disengage emergency freeze and restore signing operations."""
    return service.release_kill_switch()


@router.get(
    "/kill-switch/status",
    response_model=KillSwitchStatusResponseDTO,
    summary="Get emergency kill-switch status",
)
def get_kill_switch_status(
    service: AutonomousSigningAirgapService = Depends(
        get_autonomous_signing_airgap_service
    ),
) -> KillSwitchStatusResponseDTO:
    """Check whether emergency freeze is currently active."""
    return service.get_kill_switch_status()


@router.get(
    "/quota",
    response_model=QuotaConfigResponseDTO,
    summary="Get active signing quota configuration",
)
def get_quota_config(
    service: AutonomousSigningAirgapService = Depends(
        get_autonomous_signing_airgap_service
    ),
) -> QuotaConfigResponseDTO:
    """Retrieve active quota thresholds, whitelist, and usage statistics."""
    return service.get_quota_config()


@router.put(
    "/quota",
    response_model=QuotaConfigResponseDTO,
    summary="Update signing quota configuration",
)
def update_quota_config(
    request: UpdateQuotaConfigRequestDTO,
    service: AutonomousSigningAirgapService = Depends(
        get_autonomous_signing_airgap_service
    ),
) -> QuotaConfigResponseDTO:
    """Update single limit, daily cumulative limit, and trusted recipient whitelist."""
    return service.update_quota_config(request)


@router.get(
    "/metrics",
    response_model=WalletAirgapMetricsResponseDTO,
    summary="Get wallet airgap metrics",
)
def get_metrics(
    service: AutonomousSigningAirgapService = Depends(
        get_autonomous_signing_airgap_service
    ),
) -> WalletAirgapMetricsResponseDTO:
    """Fetch operational counters for signing evaluation, approvals, and rejections."""
    return service.get_metrics()
