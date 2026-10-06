"""FastAPI router for Local-First Zero-Leak Vault and Zero-Knowledge E2EE Sharing Gateway.

[INPUT]
FastAPI APIRouter, security dependencies, and local vault schemas.

[OUTPUT]
router: API endpoints exposing vault item management, DLP sanitization, and ephemeral E2EE sharing.

[POS]
API layer for client-side encrypted vault and zero-knowledge sharing gateway.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.local_first_vault import (
    CreateE2eeShareRequest,
    DecryptE2eeShareRequest,
    DecryptE2eeShareResponse,
    DlpSanitizeRequest,
    DlpSanitizeResponse,
    E2eeShareResponse,
    LocalArtifactResponse,
    RegisterLocalArtifactRequest,
)
from app.services.security.local_first_vault_service import (
    LocalFirstVaultService,
    get_local_first_vault_service,
)

router = APIRouter(prefix="/local-first-vault", tags=["local-first-vault"])


@router.post(
    "/dlp/sanitize",
    response_model=DlpSanitizeResponse,
    status_code=status.HTTP_200_OK,
    summary="Scan and redact sensitive IPs, domains, secrets, and pricing in-situ",
)
def sanitize_content(
    request: DlpSanitizeRequest,
    service: LocalFirstVaultService = Depends(get_local_first_vault_service),
) -> DlpSanitizeResponse:
    """Execute transparent in-situ DLP sanitization across text or artifact content."""
    return service.sanitize_content(request)


@router.post(
    "/artifacts",
    response_model=LocalArtifactResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register artifact under local-first physical disk invariant",
)
def register_local_artifact(
    request: RegisterLocalArtifactRequest,
    service: LocalFirstVaultService = Depends(get_local_first_vault_service),
) -> LocalArtifactResponse:
    """Store artifact metadata ensuring zero silent cloud synchronization."""
    try:
        return service.register_local_artifact(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid storage mode: {exc}",
        ) from exc


@router.get(
    "/artifacts/{artifact_id}",
    response_model=LocalArtifactResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve local artifact metadata",
)
def get_local_artifact(
    artifact_id: str,
    service: LocalFirstVaultService = Depends(get_local_first_vault_service),
) -> LocalArtifactResponse:
    """Lookup local-first artifact record by artifact_id."""
    item = service.get_local_artifact(artifact_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{artifact_id}' not found.",
        )
    return item


@router.get(
    "/artifacts",
    response_model=list[LocalArtifactResponse],
    status_code=status.HTTP_200_OK,
    summary="List all artifacts under local-first storage",
)
def list_local_artifacts(
    service: LocalFirstVaultService = Depends(get_local_first_vault_service),
) -> list[LocalArtifactResponse]:
    """Retrieve all local-first stored artifact records."""
    return service.list_local_artifacts()


@router.post(
    "/e2ee/share",
    response_model=E2eeShareResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create zero-knowledge E2EE encrypted share envelope with in-situ DLP",
)
def create_e2ee_share(
    request: CreateE2eeShareRequest,
    service: LocalFirstVaultService = Depends(get_local_first_vault_service),
) -> E2eeShareResponse:
    """Sanitize content with DLP, encrypt with client symmetric key, and issue zero-knowledge share envelope."""
    return service.create_e2ee_share(request)


@router.post(
    "/e2ee/decrypt/{share_id}",
    response_model=DecryptE2eeShareResponse,
    status_code=status.HTTP_200_OK,
    summary="Decrypt zero-knowledge E2EE share envelope with client key",
)
def decrypt_e2ee_share(
    share_id: str,
    request: DecryptE2eeShareRequest,
    service: LocalFirstVaultService = Depends(get_local_first_vault_service),
) -> DecryptE2eeShareResponse:
    """Verify client key proof and decrypt E2EE share content."""
    try:
        return service.decrypt_e2ee_share(share_id, request)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Share envelope '{share_id}' not found or expired.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
