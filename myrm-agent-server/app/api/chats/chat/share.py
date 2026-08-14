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
``p`` field in the request body so the password never reaches the URL (CWE-598),
a successful unlock answers with a 303 See Other redirect (PRG) and issues a
short-lived HMAC unlock cookie so the page can be refreshed or revisited without
re-entering the password. Cloud: public URL; Local/Desktop: falls back to
client-side HTML export.
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.core.infra.limiter import limiter
from app.core.security.share_hmac import (
    create_share_token,
    is_password_protected,
    parse_share_token,
)
from app.core.security.share_password_page import (
    render_password_gate_html,
    resolve_gate_password,
)
from app.database.connection import get_db
from app.database.models.chat import Chat
from app.services.chat.chat_service import ChatService
from app.services.chat.share_renderer import render_share_html
from app.services.chat.share_token import (
    ChatShareClaims,
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

_UNLOCK_COOKIE_NAME = "chat_share_unlock"
_UNLOCK_SALT = "chat-share-unlock"
_UNLOCK_COOKIE_PATH = "/api/v1/public/chat-share"


def _unlock_cookie_name(token: str) -> str:
    """Per-share cookie name so concurrent password shares never collide."""
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    return f"{_UNLOCK_COOKIE_NAME}_{digest}"


def _build_unlock_credential(claims: ChatShareClaims) -> str | None:
    """Issue a short-lived credential after a correct password unlock.

    Stateless HMAC token carrying the same conversation identity and expiry as
    the share token, so revisiting the link is authorized without re-entering
    the password. Returns ``None`` when the share is about to expire.
    """
    remaining = claims.exp - int(time.time())
    if remaining < 60:
        return None
    credential, _ = create_share_token(
        {"cid": claims.chat_id},
        salt=_UNLOCK_SALT,
        ttl_seconds=remaining,
        max_ttl_seconds=30 * 24 * 3600,
    )
    return credential


def _unlock_claims_from_cookie(value: str) -> ChatShareClaims | None:
    """Recover share claims from a signed unlock credential, or ``None``."""
    parsed = parse_share_token(value, salt=_UNLOCK_SALT)
    if parsed is None:
        return None
    chat_id = parsed.get("cid")
    exp = parsed.get("exp")
    if not isinstance(chat_id, str) or not isinstance(exp, int):
        return None
    return ChatShareClaims(chat_id=chat_id, exp=exp, password_protected=True)


def _attach_unlock_cookie(
    response: Response,
    claims: ChatShareClaims,
    token: str,
    password: str | None,
    *,
    secure: bool,
) -> bool:
    """Set the unlock cookie after a password unlock.

    Returns ``True`` when the cookie was issued, ``False`` when skipped (no
    password or share about to expire).
    """
    if not password:
        return False
    credential = _build_unlock_credential(claims)
    if credential is None:
        return False
    response.set_cookie(
        key=_unlock_cookie_name(token),
        value=credential,
        max_age=max(0, claims.exp - int(time.time())),
        path=_UNLOCK_COOKIE_PATH,
        httponly=True,
        samesite="strict",
        secure=secure,
    )
    return True


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
    password: str | None = Depends(resolve_gate_password),
) -> HTMLResponse:
    """Serve the read-only HTML page for a valid chat share token (no auth).

    GET also accepts a ``p`` query parameter so links carrying the password in
    the URL still unlock; POST reads the password from the form body (CWE-598)
    and answers with a 303 See Other redirect (PRG) so the password never
    appears in the address bar or browser history and the page can be refreshed
    without re-submitting the form. A successful unlock also issues a short-lived
    HMAC cookie so revisiting the link (or refreshing) skips the gate; when the
    share is too close to expiry to issue the cookie the page is served directly
    so a successful unlock can never loop back to the gate.
    """
    protected = is_password_protected(token)
    claims: ChatShareClaims | None
    if protected and not password:
        unlock = request.cookies.get(_unlock_cookie_name(token))
        if unlock:
            claims = _unlock_claims_from_cookie(unlock)
        else:
            claims = None
        if claims is None:
            return HTMLResponse(render_password_gate_html(), status_code=403)
    else:
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

    secure = request.url.scheme == "https"
    if request.method == "POST":
        response = RedirectResponse(url=str(request.url.path), status_code=303)
        if _attach_unlock_cookie(response, claims, token, password, secure=secure):
            return response

    response = HTMLResponse(content=html_content, headers=_SHARE_SECURITY_HEADERS)
    _attach_unlock_cookie(response, claims, token, password, secure=secure)
    return response
