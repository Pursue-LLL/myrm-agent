"""API router for Native Credential Approvals and Precise Conversation Message Links.

[INPUT]
- CreateCredentialAskRequest, DecideCredentialAskRequest.

[OUTPUT]
- CredentialAskDto, DecideCredentialAskResponse, PendingAsksResponse.

[POS]
- Security router mounted under /security/native-credential-approvals.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.native_credential_approval import (
    ApprovalAuditRecordDto,
    CreateCredentialAskRequest,
    CredentialAskDto,
    DecideCredentialAskRequest,
    DecideCredentialAskResponse,
    PendingAsksResponse,
)
from app.services.security.native_credential_approval_service import (
    NativeCredentialApprovalService,
    get_native_credential_approval_service,
)

router = APIRouter(
    prefix="/native-credential-approvals", tags=["native-credential-approvals"]
)


@router.post(
    "/asks",
    response_model=CredentialAskDto,
    status_code=status.HTTP_201_CREATED,
)
async def create_credential_ask(
    request: CreateCredentialAskRequest,
    service: NativeCredentialApprovalService = Depends(
        get_native_credential_approval_service
    ),
) -> CredentialAskDto:
    """Create a new credential access approval request bound to conversation coordinates."""
    try:
        return service.create_ask(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.get("/asks/pending", response_model=PendingAsksResponse)
async def list_pending_asks(
    owner_id: str | None = Query(default=None, description="Optional owner filter"),
    service: NativeCredentialApprovalService = Depends(
        get_native_credential_approval_service
    ),
) -> PendingAsksResponse:
    """List pending credential approval requests waiting for human owner signoff."""
    return service.list_pending_asks(owner_id=owner_id)


@router.get("/asks/{ask_id}", response_model=CredentialAskDto)
async def get_credential_ask(
    ask_id: str,
    service: NativeCredentialApprovalService = Depends(
        get_native_credential_approval_service
    ),
) -> CredentialAskDto:
    """Retrieve details of a credential approval request including its deep link."""
    ask = service.get_ask(ask_id)
    if ask is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Credential ask '{ask_id}' not found",
        )
    return ask


@router.post(
    "/asks/{ask_id}/decide",
    response_model=DecideCredentialAskResponse,
)
async def decide_credential_ask(
    ask_id: str,
    request: DecideCredentialAskRequest,
    service: NativeCredentialApprovalService = Depends(
        get_native_credential_approval_service
    ),
) -> DecideCredentialAskResponse:
    """Approve (once or standing) or deny a pending credential request."""
    try:
        return service.decide_ask(ask_id, request)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.get("/audits", response_model=list[ApprovalAuditRecordDto])
async def list_approval_audits(
    service: NativeCredentialApprovalService = Depends(
        get_native_credential_approval_service
    ),
) -> list[ApprovalAuditRecordDto]:
    """List immutable audit log records of decided credential approvals."""
    return service.list_audit_records()
