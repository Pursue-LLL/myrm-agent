"""
[POS] app/api/security/dynamic_toolchain_provenance_router.py
[INPUT] fastapi, app.schemas.dynamic_toolchain_provenance, app.services.security.dynamic_toolchain_provenance_service
[OUTPUT] router

FastAPI router for Dynamic Toolchain Supply Chain Provenance & Pre-Install Sandbox Hardening.
Exposes endpoints for supply-chain provenance verification, AST static analysis,
and JIT least-privilege sandbox confinement profile issuance.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.dynamic_toolchain_provenance import (
    CheckPermissionRequest,
    CheckPermissionResponse,
    DynamicToolchainMetricsResponse,
    EvaluateAndInstallSkillRequest,
    ManagePublisherRequest,
    ScanASTOnlyRequest,
    ScanASTOnlyResponse,
    ToolchainVerificationDecisionResponse,
    VerifyProvenanceOnlyRequest,
    VerifyProvenanceOnlyResponse,
)
from app.services.security.dynamic_toolchain_provenance_service import (
    DynamicToolchainProvenanceService,
    get_dynamic_toolchain_provenance_service,
)

router = APIRouter(
    prefix="/dynamic-toolchain-provenance",
    tags=["Dynamic Toolchain Supply Chain Provenance & Sandbox Hardening"],
)


@router.post(
    "/evaluate-and-install",
    response_model=ToolchainVerificationDecisionResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate dynamic skill provenance, scan AST, and issue JIT sandbox confinement",
)
def evaluate_and_install_skill(
    request: EvaluateAndInstallSkillRequest,
    service: DynamicToolchainProvenanceService = Depends(get_dynamic_toolchain_provenance_service),
) -> ToolchainVerificationDecisionResponse:
    """End-to-end vetting of dynamic toolchain bundle prior to sandbox mounting."""
    return service.evaluate_and_install_skill(request)


@router.post(
    "/verify-provenance",
    response_model=VerifyProvenanceOnlyResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify cryptographic publisher signature and source SHA-256 digest",
)
def verify_provenance_only(
    request: VerifyProvenanceOnlyRequest,
    service: DynamicToolchainProvenanceService = Depends(get_dynamic_toolchain_provenance_service),
) -> VerifyProvenanceOnlyResponse:
    """Standalone provenance validation against trusted registry."""
    return service.verify_provenance_only(request)


@router.post(
    "/scan-ast",
    response_model=ScanASTOnlyResponse,
    status_code=status.HTTP_200_OK,
    summary="Perform pre-install static AST scan to detect dangerous constructs",
)
def scan_ast_only(
    request: ScanASTOnlyRequest,
    service: DynamicToolchainProvenanceService = Depends(get_dynamic_toolchain_provenance_service),
) -> ScanASTOnlyResponse:
    """Inspect Python syntax tree for forbidden execs, subprocesses, sockets, and env probes."""
    return service.scan_ast_only(request)


@router.post(
    "/publishers/register",
    response_model=bool,
    status_code=status.HTTP_200_OK,
    summary="Register a new trusted publisher identity",
)
def register_trusted_publisher(
    request: ManagePublisherRequest,
    service: DynamicToolchainProvenanceService = Depends(get_dynamic_toolchain_provenance_service),
) -> bool:
    """Add a publisher ID to the trusted provenance whitelist."""
    return service.register_trusted_publisher(request)


@router.post(
    "/publishers/revoke",
    response_model=bool,
    status_code=status.HTTP_200_OK,
    summary="Revoke a trusted publisher identity",
)
def revoke_trusted_publisher(
    request: ManagePublisherRequest,
    service: DynamicToolchainProvenanceService = Depends(get_dynamic_toolchain_provenance_service),
) -> bool:
    """Remove a publisher ID from the trusted provenance whitelist."""
    return service.revoke_trusted_publisher(request)


@router.post(
    "/confinement/check-permission",
    response_model=CheckPermissionResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate if a runtime operation is permitted under a confinement policy",
)
def check_permission(
    request: CheckPermissionRequest,
    service: DynamicToolchainProvenanceService = Depends(get_dynamic_toolchain_provenance_service),
) -> CheckPermissionResponse:
    """Verify runtime domain network call, filesystem path, or env access against JIT policy."""
    return service.check_permission(request)


@router.get(
    "/metrics",
    response_model=DynamicToolchainMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get operational metrics for toolchain provenance and AST screening",
)
def get_metrics(
    service: DynamicToolchainProvenanceService = Depends(get_dynamic_toolchain_provenance_service),
) -> DynamicToolchainMetricsResponse:
    """Retrieve cumulative statistics on verification, violations, and confinement."""
    return service.get_metrics()
