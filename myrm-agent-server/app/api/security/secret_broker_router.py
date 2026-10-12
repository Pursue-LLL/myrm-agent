"""API router for Mechanical Credential Isolation and Zero-Context Secret Replacement.

[INPUT]
- IngestSecretRequest, ResolveEgressRequest, CreateAtomicGrantRequest, ConsumeAtomicGrantRequest, RejectAtomicGrantRequest

[OUTPUT]
- JSON endpoints for credentials ingestion, egress substitution, and one-shot grant lifecycle.

[POS]
- Server routing layer under `/api/security/secret-broker`.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from myrm_agent_harness.core.security.secret_broker import (
    AtomicGrantInvalidatedError,
    EgressHostMismatchError,
    SecretBrokerError,
)

from app.schemas.secret_broker import (
    AtomicGrantDto,
    BoundSecretHandleDto,
    ConsumeAtomicGrantRequest,
    CreateAtomicGrantRequest,
    IngestSecretRequest,
    IngestSecretResponse,
    RejectAtomicGrantRequest,
    ResolveEgressRequest,
    ResolveEgressResponse,
)
from app.services.security.secret_broker_service import get_secret_broker_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/secret-broker", tags=["security-secret-broker"])


@router.post(
    "/ingest",
    response_model=IngestSecretResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a secret into egress-bound vault",
)
def ingest_secret(request: IngestSecretRequest) -> IngestSecretResponse:
    """Securely store credential, binding it to target destination host and returning opaque handle."""
    service = get_secret_broker_service()
    handle = service.ingest_secret(
        secret_name=request.secret_name,
        secret_value=request.secret_value,
        allowed_host=request.allowed_host,
    )
    return IngestSecretResponse(
        handle=handle,
        message="Secret securely ingested and bound to destination host",
    )


@router.get(
    "/handles",
    response_model=list[BoundSecretHandleDto],
    summary="List all registered secret handles",
)
def list_handles() -> list[BoundSecretHandleDto]:
    """List public metadata of all active secret handles without revealing plain secrets."""
    service = get_secret_broker_service()
    return service.list_handles()


@router.post(
    "/resolve-egress",
    response_model=ResolveEgressResponse,
    summary="Resolve and substitute secret placeholders at egress dispatch",
)
def resolve_egress(request: ResolveEgressRequest) -> ResolveEgressResponse:
    """Substitute placeholders with credentials strictly if destination host matches whitelist."""
    service = get_secret_broker_service()
    try:
        return service.resolve_egress(
            content=request.content,
            target_host=request.target_host,
        )
    except EgressHostMismatchError as exc:
        logger.warning("Egress host mismatch blocked: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except SecretBrokerError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/grants/create",
    response_model=AtomicGrantDto,
    status_code=status.HTTP_201_CREATED,
    summary="Create a one-shot atomic operation grant",
)
def create_grant(request: CreateAtomicGrantRequest) -> AtomicGrantDto:
    """Create a pending one-shot grant bound to the SHA-256 fingerprint of the operation parameters."""
    service = get_secret_broker_service()
    return service.create_grant(
        operation_name=request.operation_name,
        payload=request.payload,
        ttl_seconds=request.ttl_seconds,
    )


@router.post(
    "/grants/{grant_id}/approve",
    response_model=AtomicGrantDto,
    summary="Approve a pending operation grant",
)
def approve_grant(grant_id: str) -> AtomicGrantDto:
    """Authorize a pending one-shot grant for execution."""
    service = get_secret_broker_service()
    try:
        return service.approve_grant(grant_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except AtomicGrantInvalidatedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/grants/{grant_id}/reject",
    response_model=AtomicGrantDto,
    summary="Reject and terminally revoke an operation grant",
)
def reject_grant(grant_id: str, request: RejectAtomicGrantRequest) -> AtomicGrantDto:
    """Terminally reject a grant, preventing agent from retrying or badgering the user."""
    service = get_secret_broker_service()
    try:
        return service.reject_grant(grant_id, reason=request.reason)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/grants/{grant_id}/consume",
    summary="Verify and consume an atomic operation grant",
)
def consume_grant(grant_id: str, request: ConsumeAtomicGrantRequest) -> dict[str, str | bool]:
    """Verify parameters integrity and consume one-shot grant."""
    service = get_secret_broker_service()
    try:
        success = service.consume_grant(
            grant_id=grant_id,
            operation_name=request.operation_name,
            payload=request.payload,
        )
        return {"success": success, "grant_id": grant_id, "status": "used"}
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except AtomicGrantInvalidatedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.get(
    "/grants",
    response_model=list[AtomicGrantDto],
    summary="List all operation grants",
)
def list_grants() -> list[AtomicGrantDto]:
    """List all created operation grants and their statuses."""
    service = get_secret_broker_service()
    return service.list_grants()
