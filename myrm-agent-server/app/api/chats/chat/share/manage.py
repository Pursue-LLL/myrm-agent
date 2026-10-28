"""Conversation share management API: create, revoke and report time-limited read-only links.

[INPUT]
- app.services.chat.share_token (POS: HMAC token create/rebuild)
- app.services.chat.chat_service::ChatService (POS: chat metadata)
- app.core.security.share.share_hmac (POS: token fingerprint)
- app.core.infra.ingress (POS: public-ingress SSOT + share base resolver)

[OUTPUT]
- router: authenticated create/revoke/status endpoints

[POS]
Enables GUI users to share conversations via time-limited read-only URLs, optionally password-protected. Revocation
is per-token: the active token fingerprint is persisted on create and moved into an append-only revoked-fingerprint
set on revoke, so recreating a share for the same chat can never resurrect a previously revoked link; previously
issued (non-revoked) links keep working until their own TTL expires. The status endpoint reports the current share
state (unshared / revoked / active / password-protected) so the GUI can reopen the share dialog with the live link
and a working revoke entry; unprotected links are rebuilt deterministically from the persisted expiry,
password-protected shares return a status only (their token cannot be rebuilt because the password is never
stored). Expired links — password-protected or not — report as unshared so a past-due share never surfaces as
active. Share URLs are built from the public-ingress SSOT (falling back to the request origin) so links stay
reachable in hosted/tunneled deployments. Cloud: public URL; Local/Desktop: falls back to client-side HTML export.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.infra.ingress import resolve_share_url_base
from app.core.security.share.share_hmac import token_fingerprint
from app.database.connection import get_db
from app.database.models.chat import Chat
from app.services.chat.chat_service import ChatService
from app.services.chat.share_token import create_chat_share_token, rebuild_chat_share_token

router = APIRouter()

_DEFAULT_TTL_DAYS = 7
_MAX_TTL_DAYS = 30


class CreateChatShareRequest(BaseModel):
    ttl_days: int = Field(default=_DEFAULT_TTL_DAYS, ge=1, le=_MAX_TTL_DAYS)
    password: str | None = Field(default=None, min_length=1, max_length=64)


class CreateChatShareResponse(BaseModel):
    token: str
    share_url: str
    expires_at: int
    chat_id: str
    password_protected: bool = False


@router.post("/{chat_id}/share", response_model=CreateChatShareResponse)
async def create_chat_share(
    request: Request,
    chat_id: str,
    body: CreateChatShareRequest,
    db: AsyncSession = Depends(get_db),
) -> CreateChatShareResponse:
    """Create a time-limited read-only share link for a conversation."""
    chat = await ChatService.get_chat_metadata(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    ttl_seconds = body.ttl_days * 24 * 3600
    token, expires_at = create_chat_share_token(
        chat_id,
        ttl_seconds=ttl_seconds,
        password=body.password,
    )

    # Persist the active token fingerprint and its display metadata so revoke
    # can permanently retire it and the GUI can surface the current share state
    # (rebuilding unprotected links deterministically). A fresh share does not
    # touch previously issued links (they stay valid until their own TTL expires
    # or the chat is revoked, matching pre-existing behaviour). Recreating after
    # a revoke only clears the chat-level flag; the revoked-fingerprint set is
    # left untouched so old tokens stay dead.
    values: dict[str, object] = {
        "share_token_fingerprint": token_fingerprint(token),
        "share_token_expires_at": expires_at,
        "share_token_protected": body.password is not None,
    }
    if chat.share_revoked_at is not None:
        values["share_revoked_at"] = None
    stmt = update(Chat).where(Chat.id == chat_id).values(**values)
    await db.execute(stmt)
    await db.commit()

    base_url = await resolve_share_url_base(fallback=str(request.base_url).rstrip("/"))
    share_url = f"{base_url}/api/v1/public/chat-share/{token}"

    return CreateChatShareResponse(
        token=token,
        share_url=share_url,
        expires_at=expires_at,
        chat_id=chat_id,
        password_protected=body.password is not None,
    )


@router.delete("/{chat_id}/share", status_code=204)
async def revoke_chat_share(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Revoke all active share links for a conversation."""
    chat = await ChatService.get_chat_metadata(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    revoked = list(chat.share_revoked_fingerprints or [])
    active = chat.share_token_fingerprint
    if active and active not in revoked:
        revoked.append(active)
    values: dict[str, object] = {
        "share_revoked_at": datetime.now(timezone.utc),
        "share_token_fingerprint": None,
    }
    if revoked:
        values["share_revoked_fingerprints"] = revoked
    stmt = update(Chat).where(Chat.id == chat_id).values(**values)
    await db.execute(stmt)
    await db.commit()
    return Response(status_code=204)


class ChatShareStatusResponse(BaseModel):
    """Current share state for a conversation (management GUI)."""

    shared: bool = False
    revoked: bool = False
    password_protected: bool = False
    share_url: str | None = None
    expires_at: int | None = None


@router.get("/{chat_id}/share", response_model=ChatShareStatusResponse)
async def get_chat_share_status(
    request: Request,
    chat_id: str,
    db: AsyncSession = Depends(get_db),
) -> ChatShareStatusResponse:
    """Return the current share state so the GUI can surface it on reopen.

    Four states: unshared (never shared or link already expired — expired
    links are unshared regardless of password protection), revoked (all links
    withdrawn), active (unprotected: the link is rebuilt deterministically
    from the persisted expiry so it stays copyable), and password-protected
    (the link cannot be rebuilt because the password is never stored — only a
    status is returned). The revoked flag is reported first: a revoked chat
    must never look active even if stale display metadata remains.
    """
    chat = await ChatService.get_chat_metadata(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if chat.share_revoked_at is not None:
        return ChatShareStatusResponse(shared=True, revoked=True)

    if chat.share_token_fingerprint is None:
        return ChatShareStatusResponse()

    protected = chat.share_token_protected is True
    expires_at = chat.share_token_expires_at
    # Expired links are unshared regardless of protection: a past-due share
    # must never surface as active/password-protected when it cannot be opened.
    if expires_at is not None and expires_at <= int(datetime.now(timezone.utc).timestamp()):
        return ChatShareStatusResponse()

    if protected or expires_at is None:
        return ChatShareStatusResponse(shared=True, password_protected=protected)

    token = rebuild_chat_share_token(chat_id, expires_at_unix=expires_at)
    base_url = await resolve_share_url_base(fallback=str(request.base_url).rstrip("/"))
    return ChatShareStatusResponse(
        shared=True,
        share_url=f"{base_url}/api/v1/public/chat-share/{token}",
        expires_at=expires_at,
    )
