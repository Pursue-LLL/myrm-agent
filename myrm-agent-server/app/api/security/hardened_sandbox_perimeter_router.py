"""
[POS] app/api/security/hardened_sandbox_perimeter_router.py
[INPUT] app.schemas.hardened_sandbox_perimeter, app.services.security.hardened_sandbox_perimeter_service
[OUTPUT] router

FastAPI router for Scale-Ready Hardened Agent Sandbox & Safety Perimeter Suite.
Exposes REST endpoints to validate sandbox runtime specifications, evaluate outbound network
connections against SSRF filters, broker ephemeral capability tokens, and monitor cgroups v2/process limits.

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, status

from app.schemas.hardened_sandbox_perimeter import (
    CredentialTicketMintRequest,
    CredentialTicketMintResponse,
    CredentialTicketVerifyRequest,
    CredentialTicketVerifyResponse,
    EgressEvaluateRequest,
    EgressEvaluateResponse,
    HardenedSandboxSpecRequest,
    ProcessUsageEvaluateRequest,
    ProcessUsageEvaluateResponse,
    RuntimeSpecValidationResponse,
    SandboxSafetyMetricsResponse,
)
from app.services.security.hardened_sandbox_perimeter_service import (
    HardenedSandboxPerimeterService,
    get_hardened_sandbox_perimeter_service,
)

router = APIRouter(
    prefix="/hardened-sandbox",
    tags=["Hardened Sandbox & Safety Perimeter"],
)


@router.post(
    "/validate-spec",
    response_model=RuntimeSpecValidationResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate proposed sandbox container or MicroVM operational specification",
)
def validate_spec(
    request: HardenedSandboxSpecRequest,
    service: HardenedSandboxPerimeterService = Depends(get_hardened_sandbox_perimeter_service),
) -> RuntimeSpecValidationResponse:
    """Validate sandbox runtime parameters against non-root, read-only rootfs, and cgroups bounds."""
    return service.validate_runtime_spec(request)


@router.post(
    "/evaluate-egress",
    response_model=EgressEvaluateResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate an outbound connection request to intercept SSRF and unauthorized targets",
)
def evaluate_egress(
    request: EgressEvaluateRequest,
    service: HardenedSandboxPerimeterService = Depends(get_hardened_sandbox_perimeter_service),
) -> EgressEvaluateResponse:
    """Assess outbound network traffic against RFC 1918 private subnets, cloud metadata, and allowlists."""
    return service.evaluate_egress(request)


@router.post(
    "/credentials/mint-ticket",
    response_model=CredentialTicketMintResponse,
    status_code=status.HTTP_200_OK,
    summary="Mint a short-lived scoped ephemeral ticket without exposing master credentials",
)
def mint_credential_ticket(
    request: CredentialTicketMintRequest,
    service: HardenedSandboxPerimeterService = Depends(get_hardened_sandbox_perimeter_service),
) -> CredentialTicketMintResponse:
    """Issue ephemeral access ticket to sandbox runtime without placing plaintext keys into environment."""
    return service.mint_credential_ticket(request)


@router.post(
    "/credentials/verify-ticket",
    response_model=CredentialTicketVerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify ephemeral ticket validity and scope authorization",
)
def verify_credential_ticket(
    request: CredentialTicketVerifyRequest,
    service: HardenedSandboxPerimeterService = Depends(get_hardened_sandbox_perimeter_service),
) -> CredentialTicketVerifyResponse:
    """Check whether a ticket is active, unexpired, and authorized for the requested operation scope."""
    return service.verify_credential_ticket(request)


@router.post(
    "/process-guard/evaluate",
    response_model=ProcessUsageEvaluateResponse,
    status_code=status.HTTP_200_OK,
    summary="Assess process hierarchy and resource metrics for fork-bombs and OOM risks",
)
def evaluate_process_usage(
    request: ProcessUsageEvaluateRequest,
    service: HardenedSandboxPerimeterService = Depends(get_hardened_sandbox_perimeter_service),
) -> ProcessUsageEvaluateResponse:
    """Evaluate runtime process telemetry against cgroups v2 limits and detect anomalous fork-bomb expansion."""
    return service.evaluate_process_usage(request)


@router.post(
    "/process-guard/reset/{agent_id}",
    response_model=dict[str, bool],
    status_code=status.HTTP_200_OK,
    summary="Reset tripped process guard circuit breaker for an agent",
)
def reset_process_guard(
    agent_id: str = Path(..., min_length=1, description="Agent identifier"),
    service: HardenedSandboxPerimeterService = Depends(get_hardened_sandbox_perimeter_service),
) -> dict[str, bool]:
    """Clear circuit breaker tripped state following remediation."""
    was_reset = service.reset_process_guard(agent_id)
    return {"was_reset": was_reset}


@router.get(
    "/metrics",
    response_model=SandboxSafetyMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect sandbox perimeter security telemetry metrics",
)
def get_metrics(
    service: HardenedSandboxPerimeterService = Depends(get_hardened_sandbox_perimeter_service),
) -> SandboxSafetyMetricsResponse:
    """Retrieve cumulative statistics for spec validations, SSRF blocks, credential tickets, and fork-bomb mitigations."""
    return service.get_metrics()
