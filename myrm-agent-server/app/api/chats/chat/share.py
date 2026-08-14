"""Conversation share API: create, revoke, and serve public read-only links.

[INPUT]
- app.services.chat.share_token (POS: HMAC token create/parse)
- app.services.chat.share_renderer (POS: HTML generation)
- app.services.chat.chat_service::ChatService (POS: chat metadata)
- app.core.security.share_hmac (POS: password-protection detection)
- app.core.security.share_headers (POS: shared share privacy headers)
- app.core.security.share_password_page (POS: password gate HTML + submission parsing)
- app.core.security.share_unlock (POS: shared unlock-cookie credential mechanics)
- app.core.infra.ingress (POS: public-ingress SSOT + share base resolver)

[OUTPUT]
- router: authenticated create/revoke endpoints
- public_router: unauthenticated HTML share page

[POS]
Enables GUI users to share conversations via time-limited read-only URLs.
Supports optional password-protected share links; the password gate posts its
``p`` field in the request body so the password never reaches the URL (CWE-598),
a successful unlock answers with a 303 See Other redirect (PRG) and issues a
short-lived HMAC unlock cookie so the page can be refreshed or revisited without
re-entering the password. Every served chat content page carries
noindex/nofollow + no-store + Referrer-Policy: no-referrer (shared privacy
headers) so shared conversations are never search-engine indexed, revoking a
link cannot be bypassed by browser or CDN caches, and the token-bearing share
URL never leaks to third parties via the Referer header. Share URLs are built
from the public-ingress SSOT (falling back to the request origin) so links stay
reachable in hosted/tunneled deployments. Cloud: public URL; Local/Desktop:
falls back to client-side HTML export.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.core.infra.ingress import resolve_share_url_base
from app.core.infra.limiter import limiter
from app.core.security.share_headers import SHARE_PRIVACY_HEADERS
from app.core.security.share_hmac import is_password_protected
from app.core.security.share_password_page import (
    render_password_gate_html,
    resolve_gate_password,
)
from app.core.security.share_unlock import (
    attach_unlock_cookie,
    parse_unlock_credential,
    unlock_cookie_name,
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

logger = logging.getLogger(__name__)

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

# Applied to every served chat share page via _SHARE_RESPONSE_HEADERS.
_SHARE_RESPONSE_HEADERS: dict[str, str] = {
    **_SHARE_SECURITY_HEADERS,
    **SHARE_PRIVACY_HEADERS,
}

_UNLOCK_COOKIE_NAME = "chat_share_unlock"
_UNLOCK_SALT = "chat-share-unlock"
_UNLOCK_COOKIE_PATH = "/api/v1/public/chat-share"


def _unlock_claims_from_cookie(value: str) -> ChatShareClaims | None:
    """Recover conversation share claims from a signed unlock credential."""
    parsed = parse_unlock_credential(value, salt=_UNLOCK_SALT)
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
    return attach_unlock_cookie(
        response,
        cookie_prefix=_UNLOCK_COOKIE_NAME,
        salt=_UNLOCK_SALT,
        path=_UNLOCK_COOKIE_PATH,
        payload={"cid": claims.chat_id},
        exp=claims.exp,
        token=token,
        password=password,
        secure=secure,
    )


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

    base_url = await resolve_share_url_base(
        fallback=str(request.base_url).rstrip("/")
    )
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
        unlock = request.cookies.get(unlock_cookie_name(_UNLOCK_COOKIE_NAME, token))
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

    response = HTMLResponse(content=html_content, headers=_SHARE_RESPONSE_HEADERS)
    _attach_unlock_cookie(response, claims, token, password, secure=secure)
    return response
