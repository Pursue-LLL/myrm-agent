"""Ephemeral credential staging endpoint for tool approval subsystem.

[INPUT]
- app.services.approvals.registry::ApprovalRegistry (POS: Approval record lookup)
- myrm_agent_harness.api::EphemeralCredentialStore, get_ephemeral_credential_store, validate_credential_key

[OUTPUT]
- POST /api/v1/approvals/{approval_id}/credentials: Staging masked credentials in memory

[POS]
app/api/approvals/credentials.py
Business layer endpoint for zero-leakage, zero-disk credential staging.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from myrm_agent_harness.api import (
    get_ephemeral_credential_store,
    validate_credential_key,
)
from pydantic import BaseModel, Field

from app.services.approvals.registry import ApprovalRegistry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["approvals-credentials"])


class StagedCredentialInput(BaseModel):
    """Payload for staging an ephemeral credential."""

    key: str = Field(..., description="Credential environment key name (e.g., DB_PASSWORD)")
    secret: str = Field(..., description="Plaintext secret material to stage in memory")
    ttl_seconds: float = Field(60.0, description="Time-to-live before automatic zeroization")
    single_use: bool = Field(True, description="Whether to wipe memory after single consumption")
    client_nonce: str | None = Field(None, description="Optional idempotency key preventing replay")


class StageCredentialsRequest(BaseModel):
    """Batch request for staging ephemeral credentials against an approval."""

    credentials: list[StagedCredentialInput]


class StagedCredentialItem(BaseModel):
    """Metadata response for a staged credential (no secret returned)."""

    handle_id: str
    key: str
    created_at: float
    expires_at: float
    single_use: bool


class StageCredentialsResponse(BaseModel):
    """Response containing staged credential handles."""

    approval_id: str
    session_id: str
    staged: list[StagedCredentialItem]


@router.post(
    "/{approval_id}/credentials",
    response_model=StageCredentialsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def stage_approval_credentials(
    approval_id: str,
    req: StageCredentialsRequest,
) -> StageCredentialsResponse:
    """Stage masked credentials into session memory for single-use tool execution.

    Secrets are stored in-memory in EphemeralCredentialStore with zero disk I/O,
    and bound to the approval's chat session.
    """
    record = await ApprovalRegistry.get_approval(approval_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval record '{approval_id}' not found.",
        )

    session_id = record.chat_id or record.thread_id or f"approval_session_{approval_id}"
    store = get_ephemeral_credential_store()

    staged_items: list[StagedCredentialItem] = []

    for item in req.credentials:
        try:
            valid_key = validate_credential_key(item.key)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            ) from e

        # Compute expected action digest if approval payload specifies command
        expected_digest: str | None = None
        cmd = record.payload.get("command") or record.payload.get("cmd")
        if isinstance(cmd, str) and cmd.strip():
            import hashlib

            expected_digest = hashlib.sha256(cmd.strip().encode("utf-8")).hexdigest()

        cred = store.store_credential(
            session_id=session_id,
            key=valid_key,
            secret=item.secret,
            ttl_seconds=item.ttl_seconds,
            single_use=item.single_use,
            expected_action_digest=expected_digest,
        )

        staged_items.append(
            StagedCredentialItem(
                handle_id=cred.handle_id,
                key=cred.key,
                created_at=cred.created_at,
                expires_at=cred.expires_at,
                single_use=cred.single_use,
            )
        )

    logger.info(
        "[APPROVAL_CREDENTIALS] Staged %d credentials for approval %s (session %s)",
        len(staged_items),
        approval_id,
        session_id,
    )

    return StageCredentialsResponse(
        approval_id=approval_id,
        session_id=session_id,
        staged=staged_items,
    )
