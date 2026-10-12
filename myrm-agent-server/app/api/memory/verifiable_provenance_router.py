"""
[INPUT]: ResidencyProofRequest, PhysicalPurgeRequest, InspectPiiRequest, TokenGenerateRequest
[OUTPUT]: ResidencyProofResponse, DestructionReceiptResponse, PiiShieldResponse, TokenGenerateResponse
[POS]: myrm-agent-server/app/api/memory/verifiable_provenance_router.py
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from myrm_agent_harness.toolkits.memory.verifiable_provenance import FailClosedSecurityException

from app.schemas.verifiable_provenance import (
    DestructionReceiptResponse,
    InspectPiiRequest,
    PhysicalPurgeRequest,
    PiiShieldResponse,
    ResidencyProofRequest,
    ResidencyProofResponse,
    TokenGenerateRequest,
    TokenGenerateResponse,
)
from app.services.memory.verifiable_provenance_service import VerifiableProvenanceService

router = APIRouter(prefix="/provenance", tags=["memory-provenance"])
_service = VerifiableProvenanceService()


def get_provenance_service() -> VerifiableProvenanceService:
    """Dependency injection helper returning the active VerifiableProvenanceService."""
    return _service


@router.post(
    "/token",
    response_model=TokenGenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_volume_token(
    req: TokenGenerateRequest,
) -> TokenGenerateResponse:
    """Issue cryptographically signed environment token for tenant sandbox volume binding."""
    return get_provenance_service().generate_token(req)


@router.post(
    "/residency-proof",
    response_model=ResidencyProofResponse,
    status_code=status.HTTP_200_OK,
)
async def prove_physical_residency(
    req: ResidencyProofRequest,
) -> ResidencyProofResponse:
    """Verify and return transparent physical residency proof for isolated volume storage."""
    try:
        return get_provenance_service().prove_residency(req)
    except FailClosedSecurityException as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Fail-Closed security rejection: {exc}",
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/purge",
    response_model=DestructionReceiptResponse,
    status_code=status.HTTP_200_OK,
)
async def purge_physical_storage(
    req: PhysicalPurgeRequest,
) -> DestructionReceiptResponse:
    """Execute verifiable multi-pass physical purge and return destruction receipt."""
    try:
        return get_provenance_service().purge_storage(req)
    except FailClosedSecurityException as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Fail-Closed security rejection: {exc}",
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/inspect-pii",
    response_model=PiiShieldResponse,
    status_code=status.HTTP_200_OK,
)
async def inspect_pii_content(
    req: InspectPiiRequest,
) -> PiiShieldResponse:
    """Inspect text for children identities, home addresses, and financials prior to persistence."""
    return get_provenance_service().inspect_pii(req)
