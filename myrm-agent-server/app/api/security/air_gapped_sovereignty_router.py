"""
[POS] app/api/security/air_gapped_sovereignty_router.py
[INPUT] app.schemas.air_gapped_sovereignty, app.services.security.air_gapped_sovereignty_service
[OUTPUT] router

FastAPI router for Air-Gapped Offline Trust Store & Sovereign Model Fallback Suite.
Exposes REST endpoints to manage offline root CA validations, CRL import,
sovereign model resolution under isolation, evidentiary audit bundles, and SM3 hashing.

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.air_gapped_sovereignty import (
    AirGappedSovereigntyMetricsResponse,
    AuditBundlePackRequest,
    AuditBundleResponse,
    AuditBundleVerifyRequest,
    AuditBundleVerifyResponse,
    ImportCrlRequest,
    ImportCrlResponse,
    ModelResolutionRequest,
    ModelResolutionResponse,
    ModeResponse,
    ModeUpdateRequest,
    OfflineCertValidationRequest,
    OfflineCertValidationResponse,
    SovereignCryptoHashRequest,
    SovereignCryptoHashResponse,
)
from app.services.security.air_gapped_sovereignty_service import (
    AirGappedSovereigntyService,
    get_air_gapped_sovereignty_service,
)

router = APIRouter(
    prefix="/air-gapped-sovereignty",
    tags=["Air-Gapped Offline Trust & Sovereign Model Fallback"],
)


@router.get(
    "/mode",
    response_model=ModeResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current network connectivity and isolation mode",
)
def get_network_mode(
    service: AirGappedSovereigntyService = Depends(get_air_gapped_sovereignty_service),
) -> ModeResponse:
    """Retrieve operational environment mode (ONLINE, AIR_GAPPED_ISOLATED, DEGRADED_FAILOVER)."""
    return service.get_network_mode()


@router.put(
    "/mode",
    response_model=ModeResponse,
    status_code=status.HTTP_200_OK,
    summary="Update network connectivity and isolation mode",
)
def set_network_mode(
    request: ModeUpdateRequest,
    service: AirGappedSovereigntyService = Depends(get_air_gapped_sovereignty_service),
) -> ModeResponse:
    """Configure active network isolation mode."""
    return service.set_network_mode(request)


@router.post(
    "/validate-cert",
    response_model=OfflineCertValidationResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate certificate against offline root trust anchors and CRL",
)
def validate_offline_certificate(
    request: OfflineCertValidationRequest,
    service: AirGappedSovereigntyService = Depends(get_air_gapped_sovereignty_service),
) -> OfflineCertValidationResponse:
    """Check certificate validity without online OCSP queries."""
    return service.validate_offline_certificate(request)


@router.post(
    "/import-crl",
    response_model=ImportCrlResponse,
    status_code=status.HTTP_200_OK,
    summary="Import revoked certificate serials list into offline CRL",
)
def import_crl(
    request: ImportCrlRequest,
    service: AirGappedSovereigntyService = Depends(get_air_gapped_sovereignty_service),
) -> ImportCrlResponse:
    """Update offline CRL bundle with new blacklisted serials."""
    return service.import_crl(request)


@router.post(
    "/resolve-model",
    response_model=ModelResolutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Resolve execution model target under isolation and failover policies",
)
def resolve_model(
    request: ModelResolutionRequest,
    service: AirGappedSovereigntyService = Depends(get_air_gapped_sovereignty_service),
) -> ModelResolutionResponse:
    """Enforce sovereign model routing or seamless local fallback."""
    return service.resolve_model(request)


@router.post(
    "/pack-audit-bundle",
    response_model=AuditBundleResponse,
    status_code=status.HTTP_200_OK,
    summary="Seal audit records into tamper-evident SM3 evidentiary archive bundle",
)
def pack_audit_bundle(
    request: AuditBundlePackRequest,
    service: AirGappedSovereigntyService = Depends(get_air_gapped_sovereignty_service),
) -> AuditBundleResponse:
    """Cryptographically seal agent execution logs using SM3 Merkle root digest."""
    return service.pack_audit_bundle(request)


@router.post(
    "/verify-audit-bundle",
    response_model=AuditBundleVerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify evidentiary audit bundle integrity against raw records",
)
def verify_audit_bundle(
    request: AuditBundleVerifyRequest,
    service: AirGappedSovereigntyService = Depends(get_air_gapped_sovereignty_service),
) -> AuditBundleVerifyResponse:
    """Cross-examine raw event records against sealed bundle's root digest."""
    return service.verify_audit_bundle(request)


@router.post(
    "/hash/sm3",
    response_model=SovereignCryptoHashResponse,
    status_code=status.HTTP_200_OK,
    summary="Compute commercial GM/T SM3 cryptographic digest",
)
def compute_sm3_hash(
    request: SovereignCryptoHashRequest,
    service: AirGappedSovereigntyService = Depends(get_air_gapped_sovereignty_service),
) -> SovereignCryptoHashResponse:
    """Compute 256-bit SM3 digest for input string."""
    return service.compute_sm3_hash(request)


@router.get(
    "/metrics",
    response_model=AirGappedSovereigntyMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve cumulative telemetry metrics for air-gapped sovereignty subsystem",
)
def get_metrics(
    service: AirGappedSovereigntyService = Depends(get_air_gapped_sovereignty_service),
) -> AirGappedSovereigntyMetricsResponse:
    """Inspect cumulative validation events, CRL hits, fallbacks, and sealed bundles."""
    return service.get_metrics()
