"""One-time credential staging for the command a tool approval card asks about.

[INPUT]
- app.services.agent.params.workspace_resolve::chat_session_id (POS: the session key of a chat's agent runs)
- myrm_agent_harness.api::command_digest, get_ephemeral_credential_store, validate_credential_key

[OUTPUT]
- POST /api/v1/approvals/credentials: stage credentials in memory for one command of one chat
- POST /api/v1/approvals/credentials/wipe: discard staged credentials the user took back

[POS]
app/api/approvals/credentials.py
Business layer endpoints for zero-leakage, zero-disk credential staging. A credential is bound to the digest of the
command the user is looking at and to the session of the chat that asked, so only that command, in that chat, can
ever read it.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from myrm_agent_harness.api import (
    command_digest,
    get_ephemeral_credential_store,
    validate_credential_key,
)
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["approvals-credentials"])

_MAX_TTL_SECONDS = 600.0


class StagedCredentialInput(BaseModel):
    """One credential to stage."""

    key: str = Field(..., description="Credential environment key name (e.g., DB_PASSWORD)")
    secret: str = Field(..., min_length=1, description="Plaintext secret material to stage in memory")
    ttl_seconds: float = Field(60.0, gt=0, le=_MAX_TTL_SECONDS, description="Time-to-live before zeroization")
    single_use: bool = Field(True, description="Whether to wipe memory after single consumption")


class StageCredentialsRequest(BaseModel):
    """Credentials for the one command an approval card shows."""

    chat_id: str = Field(..., min_length=1, description="Chat whose agent run asked for the approval")
    command: str = Field(..., min_length=1, description="The command text exactly as the approval card shows it")
    credentials: list[StagedCredentialInput] = Field(..., min_length=1)


class StagedCredentialItem(BaseModel):
    """Metadata response for a staged credential (no secret returned)."""

    handle_id: str
    key: str
    created_at: float
    expires_at: float
    single_use: bool


class StageCredentialsResponse(BaseModel):
    """Handles of the staged credentials."""

    staged: list[StagedCredentialItem]


class WipeCredentialsRequest(BaseModel):
    """Staged credentials the user took back."""

    chat_id: str = Field(..., min_length=1)
    handle_ids: list[str] = Field(..., min_length=1)


class WipeCredentialsResponse(BaseModel):
    """How many of the requested handles were still staged."""

    wiped: int


def _session_key(chat_id: str) -> str:
    from app.services.agent.params.workspace_resolve import chat_session_id

    return chat_session_id(chat_id)


@router.post(
    "/credentials",
    response_model=StageCredentialsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def stage_command_credentials(req: StageCredentialsRequest) -> StageCredentialsResponse:
    """Stage credentials in session memory for single-use delivery to one approved command.

    Secrets live only in ``EphemeralCredentialStore`` (no disk I/O). The command digest is computed by the same
    harness function the executor checks it with, so a command that is edited after staging gets nothing.
    """
    if not req.command.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Command must not be blank.")

    try:
        keys = [validate_credential_key(item.key) for item in req.credentials]
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

    session_id = _session_key(req.chat_id)
    digest = command_digest(req.command)
    store = get_ephemeral_credential_store()

    staged_items: list[StagedCredentialItem] = []
    for key, item in zip(keys, req.credentials, strict=True):
        cred = store.store_credential(
            session_id=session_id,
            key=key,
            secret=item.secret,
            ttl_seconds=item.ttl_seconds,
            single_use=item.single_use,
            expected_action_digest=digest,
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

    logger.info("[APPROVAL_CREDENTIALS] Staged %d credentials for chat %s", len(staged_items), req.chat_id)
    return StageCredentialsResponse(staged=staged_items)


@router.post("/credentials/wipe", response_model=WipeCredentialsResponse)
async def wipe_command_credentials(req: WipeCredentialsRequest) -> WipeCredentialsResponse:
    """Zeroize staged credentials of a chat that the user revoked or whose approval was rejected or edited."""
    wiped = get_ephemeral_credential_store().wipe_handles(_session_key(req.chat_id), req.handle_ids)
    logger.info("[APPROVAL_CREDENTIALS] Wiped %d staged credentials for chat %s", wiped, req.chat_id)
    return WipeCredentialsResponse(wiped=wiped)
