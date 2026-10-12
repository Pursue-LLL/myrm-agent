"""
[POS] app/api/security/request_secret_router.py
[INPUT] fastapi, app.schemas.request_secret, app.services.security.request_secret_service
[OUTPUT] request_secret_router
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from myrm_agent_harness.core.security.request_secret import IncompleteCredentialError

from app.schemas.request_secret import (
    CreateSecretCardRequestDTO,
    FulfillSecretCardRequestDTO,
    MaskedCredentialRefDTO,
    RegisterSavedCredentialRequestDTO,
    RejectSecretCardRequestDTO,
    SanitizedSecretResultDTO,
    SecretCardSessionDTO,
)
from app.services.security.request_secret_service import (
    RequestSecretService,
    get_request_secret_service,
)

router = APIRouter(
    prefix="/request-secret",
    tags=["Request-Secret Masked Credential Card Suite"],
)


@router.post(
    "/create",
    response_model=SecretCardSessionDTO,
    summary="Create a new interactive secret request card session",
)
def create_secret_card(
    request: CreateSecretCardRequestDTO,
    service: RequestSecretService = Depends(get_request_secret_service),
) -> SecretCardSessionDTO:
    """Create a structured request card for user to provide or backfill a task-scoped secret."""
    return service.create_card_session(request)


@router.post(
    "/fulfill",
    response_model=SanitizedSecretResultDTO,
    summary="Fulfill an active secret card with plaintext input or saved backfill",
)
def fulfill_secret_card(
    request: FulfillSecretCardRequestDTO,
    service: RequestSecretService = Depends(get_request_secret_service),
) -> SanitizedSecretResultDTO:
    """Validate submission, filter planted fields, and return sanitized transcript-safe result."""
    try:
        return service.fulfill_card(request)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except (IncompleteCredentialError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/reject",
    response_model=SecretCardSessionDTO,
    summary="Reject an active secret card session",
)
def reject_secret_card(
    request: RejectSecretCardRequestDTO,
    service: RequestSecretService = Depends(get_request_secret_service),
) -> SecretCardSessionDTO:
    """Explicitly reject a secret request card."""
    try:
        return service.reject_card(request)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/card/{card_id}",
    response_model=SecretCardSessionDTO,
    summary="Get status and details of a secret card session",
)
def get_secret_card(
    card_id: str,
    service: RequestSecretService = Depends(get_request_secret_service),
) -> SecretCardSessionDTO:
    """Fetch secret card session metadata and current lifecycle status."""
    session = service.get_card_session(card_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Secret card '{card_id}' not found",
        )
    return session


@router.post(
    "/saved/register",
    response_model=MaskedCredentialRefDTO,
    summary="Register a saved credential in vault",
)
def register_saved_credential(
    request: RegisterSavedCredentialRequestDTO,
    service: RequestSecretService = Depends(get_request_secret_service),
) -> MaskedCredentialRefDTO:
    """Store credential in secure vault and return its safe masked fingerprint reference."""
    return service.register_saved_credential(request)


@router.get(
    "/saved/list",
    response_model=list[MaskedCredentialRefDTO],
    summary="List available masked credential references",
)
def list_saved_credentials(
    target_system: str | None = Query(default=None, description="Optional target system filter"),
    service: RequestSecretService = Depends(get_request_secret_service),
) -> list[MaskedCredentialRefDTO]:
    """Return all safe masked credentials available for user backfill."""
    return service.list_saved_credentials(target_system=target_system)
