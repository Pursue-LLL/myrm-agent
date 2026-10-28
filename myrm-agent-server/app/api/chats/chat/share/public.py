"""Public read-only conversation share page with the password gate.

[INPUT]
- app.services.chat.share_token (POS: HMAC token parse)
- app.services.chat.share_renderer (POS: HTML generation)
- app.services.chat.chat_service::ChatService (POS: chat metadata)
- app.core.security.share.share_hmac (POS: password-protection detection)
- app.core.security.share.share_attempt_guard (POS: wrong-password lockout for the gate)
- app.core.security.share.share_headers (POS: shared share privacy headers)
- app.core.security.share.share_password_page (POS: password gate HTML + submission parsing)
- app.core.security.share.share_status_page (POS: browser-friendly share 404 page)
- app.core.security.share.share_unlock (POS: shared unlock-cookie credential mechanics)

[OUTPUT]
- public_router: unauthenticated HTML share page

[POS]
Serves a shared conversation to anyone holding the link. Supports optional password-protected share links; the
password gate posts its ``p`` field in the request body so the password never reaches the URL (CWE-598), a successful
unlock answers with a 303 See Other redirect (PRG) and issues a short-lived HMAC unlock cookie so the page can be
refreshed or revisited without re-entering the password. Revoked or deleted links are retired before the password
gate, so a dead password-protected link answers 404 to every visitor instead of presenting a password prompt for
content that no longer exists. Wrong passwords are counted per share and client; after five the gate answers 429 with
``Retry-After`` and refuses further guesses (even a correct one) until the window passes, while visitors holding an
unlock cookie keep their access. Every served chat content page carries noindex/nofollow + no-store +
Referrer-Policy: no-referrer (shared privacy headers) so shared conversations are never search-engine indexed,
revoking a link cannot be bypassed by browser or CDN caches, and the token-bearing share URL never leaks to third
parties via the Referer header. Expired, revoked, or missing share links answer browsers with a friendly status page
(and API clients with the JSON 404 contract) so link lifecycle failures never surface as raw JSON to end users.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.share.share_attempt_guard import (
    password_lockout_response,
    record_password_failure,
    record_password_success,
)
from app.core.security.share.share_headers import SHARE_PRIVACY_HEADERS
from app.core.security.share.share_hmac import (
    decode_unverified_payload,
    is_password_protected,
    token_fingerprint,
)
from app.core.security.share.share_password_page import (
    password_gate_response,
    resolve_gate_password,
)
from app.core.security.share.share_status_page import ShareLinkState, share_not_found
from app.core.security.share.share_unlock import (
    attach_unlock_cookie,
    parse_unlock_credential,
    unlock_cookie_name,
)
from app.database.connection import get_db
from app.database.dto import ChatDTO
from app.services.audit.lockout_events import report_share_lockout
from app.services.chat.chat_service import ChatService
from app.services.chat.share_renderer import render_share_html
from app.services.chat.share_token import ChatShareClaims, parse_chat_share_token

public_router = APIRouter()

_SHARE_SECURITY_HEADERS: dict[str, str] = {
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; frame-src 'none'; object-src 'none'"
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


def _decode_share_claims_unverified(token: str) -> ChatShareClaims | None:
    """Decode token claims without verifying the HMAC signature.

    The payload is base64-encoded JSON — only the signature requires the
    password — so the chat id is readable before a visitor unlocks a protected
    share. This is used solely to look up the share lifecycle state so a
    revoked or deleted link answers 404 instead of presenting as alive behind
    the password gate.
    """
    raw = decode_unverified_payload(token)
    if raw is None:
        return None
    chat_id = raw.get("cid")
    exp = raw.get("exp")
    if not isinstance(chat_id, str) or not isinstance(exp, int):
        return None
    return ChatShareClaims(
        chat_id=chat_id,
        exp=exp,
        password_protected=raw.get("p") == 1,
    )


def _chat_share_is_revoked(chat: ChatDTO, token: str) -> bool:
    """Whether the presented token has been revoked for this conversation."""
    revoked_fingerprints = set(chat.share_revoked_fingerprints or [])
    return chat.share_revoked_at is not None or (
        chat.share_token_fingerprint is not None and token_fingerprint(token) in revoked_fingerprints
    )


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


@public_router.get("/{token}")
@public_router.post("/{token}")
async def get_public_chat_share(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
    password: str | None = Depends(resolve_gate_password),
) -> Response:
    """Serve the read-only HTML page for a valid chat share token (no auth).

    GET also accepts a ``p`` query parameter so links carrying the password in
    the URL still unlock; POST reads the password from the form body (CWE-598)
    and answers with a 303 See Other redirect (PRG) so the password never
    appears in the address bar or browser history and the page can be refreshed
    without re-submitting the form. A successful unlock also issues a short-lived
    HMAC cookie so revisiting the link (or refreshing) skips the gate; when the
    share is too close to expiry to issue the cookie the page is served directly
    so a successful unlock can never loop back to the gate.

    Lifecycle state is resolved before the password gate: a revoked or deleted
    share answers 404 to everyone — including a visitor who has not unlocked a
    password-protected link yet — so a dead link never presents as alive behind
    a password prompt.
    """
    protected = is_password_protected(token)

    # The token payload is base64-encoded JSON (only the HMAC signature is
    # secret), so the chat id is readable pre-unlock. Look the conversation up
    # up front and retire revoked links before the gate can mask them.
    decoded = _decode_share_claims_unverified(token)
    chat = await ChatService.get_chat_metadata(decoded.chat_id) if decoded else None
    if chat is not None and _chat_share_is_revoked(chat, token):
        return share_not_found(
            request,
            detail="This share link has been revoked",
            state=ShareLinkState.REVOKED,
            headers=_SHARE_RESPONSE_HEADERS,
        )

    claims: ChatShareClaims | None
    if protected and not password:
        unlock = request.cookies.get(unlock_cookie_name(_UNLOCK_COOKIE_NAME, token))
        if unlock:
            claims = _unlock_claims_from_cookie(unlock)
        else:
            claims = None
        if claims is None:
            if decoded is not None and chat is None:
                return share_not_found(
                    request,
                    detail="Conversation not found",
                    state=ShareLinkState.CONVERSATION_UNAVAILABLE,
                    headers=_SHARE_RESPONSE_HEADERS,
                )
            return password_gate_response(request)
    else:
        guessing = protected and bool(password)
        if guessing and (locked := password_lockout_response(request, token)) is not None:
            return locked
        claims = parse_chat_share_token(token, password=password)
        if claims is None:
            if guessing:
                if record_password_failure(request, token):
                    report_share_lockout(request, token)
                return password_gate_response(request, wrong_password=True)
            return share_not_found(
                request,
                detail="Share link is invalid or expired",
                state=ShareLinkState.EXPIRED,
                headers=_SHARE_RESPONSE_HEADERS,
            )
        if guessing:
            record_password_success(request, token)

    if chat is None:
        chat = await ChatService.get_chat_metadata(claims.chat_id)
    if chat is None:
        return share_not_found(
            request,
            detail="Conversation not found",
            state=ShareLinkState.CONVERSATION_UNAVAILABLE,
            headers=_SHARE_RESPONSE_HEADERS,
        )

    html_content = await render_share_html(claims.chat_id, db)
    if html_content is None:
        return share_not_found(
            request,
            detail="Conversation not found",
            state=ShareLinkState.CONVERSATION_UNAVAILABLE,
            headers=_SHARE_RESPONSE_HEADERS,
        )

    secure = request.url.scheme == "https"
    if request.method == "POST":
        redirect = RedirectResponse(url=str(request.url.path), status_code=303)
        if _attach_unlock_cookie(redirect, claims, token, password, secure=secure):
            return redirect

    response = HTMLResponse(content=html_content, headers=_SHARE_RESPONSE_HEADERS)
    _attach_unlock_cookie(response, claims, token, password, secure=secure)
    return response
