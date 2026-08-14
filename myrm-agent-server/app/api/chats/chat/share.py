"""Conversation share API: create, revoke, and serve public read-only links.

[INPUT]
- app.services.chat.share_token (POS: HMAC token create/parse)
- app.services.chat.share_renderer (POS: HTML generation)
- app.services.chat.chat_service::ChatService (POS: chat metadata)
- app.core.security.share_hmac (POS: password-protection detection)
- app.core.security.share_password_page (POS: password gate HTML + submission parsing)

[OUTPUT]
- router: authenticated create/revoke endpoints
- public_router: unauthenticated HTML share page

[POS]
Enables GUI users to share conversations via time-limited read-only URLs.
Supports optional password-protected share links; the password gate posts its
``p`` field in the request body so the password never reaches the URL (CWE-598).
Cloud: public URL; Local/Desktop: falls back to client-side HTML export.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.core.infra.limiter import limiter
from app.core.security.share_hmac import is_password_protected
from app.core.security.share_password_page import (
    render_password_gate_html,
    resolve_gate_password,
)
from app.database.connection import get_db
from app.database.models.chat import Chat
from app.services.chat.chat_service import ChatService
from app.services.chat.share_renderer import render_share_html
from app.services.chat.share_token import (
    create_chat_share_token,
    parse_chat_share_token,
)

router = APIRouter()
public_router = APIRouter()

_DEFAULT_TTL_DAYS = 7
_MAX_TTL_DAYS = 30

_SHARE_SECURITY_HEADERS: dict[str, str] = {
    "Content-Security-Policy": (
        "default-src 'none'; "
        "style-src 'unsafe-inline'; "
        "img-src data:; "
        "font-src data:; "
        "frame-src 'none'; "
        "object-src 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


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
@limiter.limit(settings.rate_limit.chat)
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

    if chat.share_revoked_at is not None:
        stmt = update(Chat).where(Chat.id == chat_id).values(share_revoked_at=None)
        await db.execute(stmt)
        await db.commit()

    ttl_seconds = body.ttl_days * 24 * 3600
    token, expires_at = create_chat_share_token(
        chat_id, ttl_seconds=ttl_seconds, password=body.password,
    )

    base_url = str(request.base_url).rstrip("/")
    share_url = f"{base_url}/api/v1/public/chat-share/{token}"

    return CreateChatShareResponse(
        token=token,
        share_url=share_url,
        expires_at=expires_at,
        chat_id=chat_id,
        password_protected=body.password is not None,
    )


@router.delete("/{chat_id}/share", status_code=204)
@limiter.limit(settings.rate_limit.chat)
async def revoke_chat_share(
    request: Request,
    chat_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Revoke all active share links for a conversation."""
    chat = await ChatService.get_chat_metadata(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    stmt = (
        update(Chat)
        .where(Chat.id == chat_id)
        .values(share_revoked_at=datetime.now(timezone.utc))
    )
    await db.execute(stmt)
    await db.commit()
    return Response(status_code=204)


@public_router.api_route("/{token}", methods=["GET", "POST"])
@limiter.limit("30/minute")
async def get_public_chat_share(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Serve the read-only HTML page for a valid chat share token (no auth).

    GET also accepts a ``p`` query parameter so links carrying the password in
    the URL still unlock; POST reads the password from the form body (CWE-598)
    so it never appears in the URL or browser history.
    """
    protected = is_password_protected(token)
    password = await resolve_gate_password(request)
    if protected and not password:
        return HTMLResponse(render_password_gate_html(), status_code=403)

    claims = parse_chat_share_token(token, password=password)
    if claims is None:
        if protected and password:
            return HTMLResponse(
                render_password_gate_html(wrong_password=True), status_code=403,
            )
        raise HTTPException(status_code=404, detail="Share link is invalid or expired")

    chat = await ChatService.get_chat_metadata(claims.chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if chat.share_revoked_at is not None:
        raise HTTPException(status_code=404, detail="This share link has been revoked")

    html_content = await render_share_html(claims.chat_id, db)
    if html_content is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return HTMLResponse(
        content=html_content,
        headers=_SHARE_SECURITY_HEADERS,
    )
