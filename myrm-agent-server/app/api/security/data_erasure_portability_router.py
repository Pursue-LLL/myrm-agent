"""API router for Verifiable Cryptographic Erasure and Complete Data Portability.

[POS] app/api/security/data_erasure_portability_router.py
[INPUT] app/schemas/data_erasure_portability.py, app/services/security/data_erasure_portability_service.py
[OUTPUT] router
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.data_erasure_portability import (
    ErasureResultResponse,
    ExecuteErasureRequest,
    ExportPortabilityBundleRequest,
    PortabilityBundleResponse,
    RegisterTenantKeyRequest,
    ShredPathRequest,
    ShredPathResponse,
    TenantKeyResponse,
    VerifyBundleRequest,
    VerifyBundleResponse,
    VerifyCertificateRequest,
    VerifyCertificateResponse,
)
from app.services.security.data_erasure_portability_service import (
    DataErasurePortabilityService,
    get_data_erasure_portability_service,
)

router = APIRouter(prefix="/data-erasure", tags=["data-erasure-portability"])


@router.post("/keys/register", response_model=TenantKeyResponse)
async def register_tenant_key(
    req: RegisterTenantKeyRequest,
    service: DataErasurePortabilityService = Depends(get_data_erasure_portability_service),
) -> TenantKeyResponse:
    """Register or generate a tenant Data Encryption Key (DEK)."""
    return service.register_tenant_key(req)


@router.post("/purge", response_model=ErasureResultResponse)
async def purge_tenant_data(
    req: ExecuteErasureRequest,
    service: DataErasurePortabilityService = Depends(get_data_erasure_portability_service),
) -> ErasureResultResponse:
    """Execute irreversible cryptographic erasure and optional storage volume shredding."""
    return service.execute_erasure(req)


@router.post("/certificates/verify", response_model=VerifyCertificateResponse)
async def verify_deletion_certificate(
    req: VerifyCertificateRequest,
    service: DataErasurePortabilityService = Depends(get_data_erasure_portability_service),
) -> VerifyCertificateResponse:
    """Verify cryptographic authenticity of a DeletionCertificate."""
    return service.verify_certificate(req)


@router.post("/export", response_model=PortabilityBundleResponse)
async def export_portability_bundle(
    req: ExportPortabilityBundleRequest,
    service: DataErasurePortabilityService = Depends(get_data_erasure_portability_service),
) -> PortabilityBundleResponse:
    """Export complete tenant digital assets under GDPR Article 20."""
    return service.export_bundle(req)


@router.post("/export/verify", response_model=VerifyBundleResponse)
async def verify_portability_bundle(
    req: VerifyBundleRequest,
    service: DataErasurePortabilityService = Depends(get_data_erasure_portability_service),
) -> VerifyBundleResponse:
    """Verify cryptographic integrity of a portability container."""
    return service.verify_bundle(req)


@router.post("/shred-path", response_model=ShredPathResponse)
async def shred_storage_path(
    req: ShredPathRequest,
    service: DataErasurePortabilityService = Depends(get_data_erasure_portability_service),
) -> ShredPathResponse:
    """Execute multi-pass physical shredding directly on a designated path."""
    return service.shred_path(req)
