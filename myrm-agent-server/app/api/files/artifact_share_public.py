"""Unauthenticated public endpoint for artifact share bundles (entry + assets).

[INPUT]
- app.core.security.share.share_hmac (POS: HMAC signing + password-protection detection)
- app.core.security.share.share_headers (POS: shared share privacy headers)
- app.core.security.share.share_password_page (POS: password gate HTML + submission parsing)
- app.core.security.share.share_status_page (POS: browser-friendly share 404 page)
- app.core.security.share.share_unlock (POS: shared unlock-cookie credential mechanics)
- app.services.artifacts.share_bundle (POS: multi-file static bundle materialization)
- app.services.artifacts.share_registry (POS: revocation gate check)
- app.services.artifacts.share_token::ArtifactShareClaims (POS: HMAC claims)

[OUTPUT]
- public_router: unauthenticated inline file view (entry + static assets)

[POS]
Server business layer. Serves materialized share bundles to the public web with
hardened CSP headers, optional password gate, and a manual-revocation gate that
blocks both existing files and any re-materialization attempt after revoke.
Every served file carries the shared privacy headers (noindex/nofollow +
no-store + Referrer-Policy: no-referrer) so shared work products are never
search-engine indexed, revoking a link cannot be bypassed by browser or CDN
caches, and the token-bearing URL cannot leak to third-party origins via the
Referer header. Expired, revoked, or missing shares answer browsers with a
friendly status page (and API clients with the JSON 404 contract) so link
lifecycle failures never surface as raw JSON to end users. The password gate
posts its ``p`` field in the request body so the password never reaches the URL
(CWE-598); a successful unlock answers with a 303 See Other redirect (PRG) to
the clean GET URL, or serves the content directly when the share is too close
to expiry to issue an unlock cookie (no redirect loop). The HMAC unlock
credential issued after a correct password keeps the share's ``artifact_type``
so extension-less entries (e.g. a PDF artifact named without a suffix) still
resolve the right media type when the browser re-authenticates via the unlock
cookie instead of a password parameter.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_workspace_root
from app.core.infra.limiter import limiter
from app.core.security.share.share_headers import SHARE_PRIVACY_HEADERS
from app.core.security.share.share_hmac import is_password_protected
from app.core.security.share.share_password_page import (
    render_password_gate_html,
    resolve_gate_password,
)
from app.core.security.share.share_status_page import share_not_found
from app.core.security.share.share_unlock import (
    attach_unlock_cookie,
    parse_unlock_credential,
    unlock_cookie_name,
)
from app.database.connection import get_db
from app.services.artifacts.share_bundle import (
    bundle_asset_count,
    materialize_share_bundle,
    purge_expired_share_bundles,
    resolve_share_bundle_file,
)
from app.services.artifacts.share_registry import is_token_revoked
from app.services.artifacts.share_token import (
    ArtifactShareClaims,
    parse_artifact_share_token,
)

logger = logging.getLogger(__name__)

public_router = APIRouter()

_HTML_MEDIA_TYPES = frozenset(
    {"text/html", "text/html; charset=utf-8", "application/xhtml+xml"}
)

_SHARE_SECURITY_HEADERS: dict[str, str] = {
    "Content-Security-Policy": (
        "default-src 'none'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data:; "
        "media-src 'self' data: blob:; "
        "connect-src 'none'; "
        "frame-src 'none'; "
        "object-src 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}

# Applied to every served HTML share surface (content entry, status page) via
# the shared privacy headers + this module's HTML security headers.
_SHARE_RESPONSE_HEADERS: dict[str, str] = {
    **_SHARE_SECURITY_HEADERS,
    **SHARE_PRIVACY_HEADERS,
}

# Privacy headers (noindex/nofollow + no-store + no-referrer) apply to every
# served bundle file via the shared constant: shares are private, time-limited
# content, never indexed for search engines, never cached by browsers/CDNs, and
# the token-bearing URL must not leak to third parties via the Referer header.
_UNLOCK_COOKIE_NAME = "artifact_share_unlock"
_UNLOCK_SALT = "artifact-share-unlock"
_UNLOCK_COOKIE_PATH = "/api/v1/public/artifact-share"


def _file_response(path: str, media_type: str, filename: str) -> FileResponse:
    headers = dict(
        _SHARE_RESPONSE_HEADERS if media_type in _HTML_MEDIA_TYPES else SHARE_PRIVACY_HEADERS
    )
    return FileResponse(
        path=path,
        headers=headers,
        media_type=media_type,
        filename=filename,
        content_disposition_type="inline",
    )


def _unlock_claims_from_cookie(value: str) -> ArtifactShareClaims | None:
    """Recover artifact share claims from a signed unlock credential."""
    parsed = parse_unlock_credential(value, salt=_UNLOCK_SALT)
    if parsed is None:
        return None
    artifact_id = parsed.get("aid")
    version_id = parsed.get("vid")
    exp = parsed.get("exp")
    if (
        not isinstance(artifact_id, str)
        or not isinstance(version_id, str)
        or not isinstance(exp, int)
    ):
        return None
    artifact_type_raw = parsed.get("typ")
    artifact_type = artifact_type_raw if isinstance(artifact_type_raw, str) else None
    return ArtifactShareClaims(
        artifact_id=artifact_id,
        version_id=version_id,
        exp=exp,
        artifact_type=artifact_type,
    )


def _attach_unlock_cookie(
    response: Response,
    claims: ArtifactShareClaims,
    token: str,
    password: str | None,
    *,
    secure: bool,
) -> bool:
    """Set the unlock cookie after a password unlock.

    Returns ``True`` when the cookie was issued (share has enough remaining
    TTL), ``False`` when it was skipped (no password or share about to expire).
    """
    payload: dict[str, object] = {"aid": claims.artifact_id, "vid": claims.version_id}
    if claims.artifact_type and claims.artifact_type.strip():
        payload["typ"] = claims.artifact_type.strip().lower()
    return attach_unlock_cookie(
        response,
        cookie_prefix=_UNLOCK_COOKIE_NAME,
        salt=_UNLOCK_SALT,
        path=_UNLOCK_COOKIE_PATH,
        payload=payload,
        exp=claims.exp,
        token=token,
        password=password,
        secure=secure,
    )


async def _serve_share_bundle(
    claims: ArtifactShareClaims,
    db: AsyncSession,
    workspace_root: str,
    relative_path: str | None,
    request: Request,
) -> Response:
    purge_expired_share_bundles()
    resolved = resolve_share_bundle_file(claims, relative_path)
    if resolved is None:
        try:
            await materialize_share_bundle(db, workspace_root, claims)
        except (ValueError, LookupError) as exc:
            return share_not_found(
                request,
                detail=str(exc),
                title="Content Unavailable",
                message="The shared content is no longer available.",
                headers=_SHARE_RESPONSE_HEADERS,
            )
        except FileNotFoundError:
            return share_not_found(
                request,
                detail="Artifact content not found",
                title="Content Unavailable",
                message="The shared content is no longer available.",
                headers=_SHARE_RESPONSE_HEADERS,
            )
        except Exception as exc:
            logger.error("Share bundle materialize failed: %s", exc)
            raise HTTPException(
                status_code=500, detail="Failed to load shared artifact"
            ) from exc
        resolved = resolve_share_bundle_file(claims, relative_path)

    if resolved is None:
        return share_not_found(
            request,
            detail="Shared file not found",
            title="Content Unavailable",
            message="The shared file is no longer available.",
            headers=_SHARE_RESPONSE_HEADERS,
        )

    file_path, media_type, filename = resolved
    return _file_response(str(file_path), media_type, filename)


def _auth_or_gate(
    request: Request,
    token: str,
    password: str | None,
) -> ArtifactShareClaims | Response:
    """Authenticate a password-protected share using ``p`` or a prior unlock cookie.

    Returns ``ArtifactShareClaims`` on success, or a ``Response`` (password-gate
    page or 404 status page) when a password is required but missing/wrong or
    the share is invalid/expired. The unlock cookie lets static-asset requests
    (which do not carry the password) pass once unlocked.
    """
    protected = is_password_protected(token)
    if protected and not password:
        unlock = request.cookies.get(unlock_cookie_name(_UNLOCK_COOKIE_NAME, token))
        if unlock:
            unlocked_claims = _unlock_claims_from_cookie(unlock)
            if unlocked_claims is not None:
                return unlocked_claims
        return HTMLResponse(render_password_gate_html(), status_code=403)

    claims = parse_artifact_share_token(token, password=password)
    if claims is None:
        if protected and password:
            return HTMLResponse(
                render_password_gate_html(wrong_password=True),
                status_code=403,
            )
        return share_not_found(
            request,
            detail="Share link is invalid or expired",
            title="Link Expired",
            message="This share link has expired or is no longer valid.",
            headers=_SHARE_RESPONSE_HEADERS,
        )
    return claims


async def _ensure_not_revoked(
    db: AsyncSession,
    token: str,
    request: Request,
) -> Response | None:
    """Reject requests whose token has been manually revoked.

    Returns a 404 status page for revoked links (browsers) or ``None`` when the
    share is still valid. Called before token authentication on every public
    entry so a revoked share (password-protected or not) is denied immediately
    without presenting the password gate or touching the on-disk bundle.
    """
    try:
        revoked = await is_token_revoked(db, token)
    except Exception as exc:
        logger.warning("Share revocation check failed: %s", exc)
        revoked = False
    if revoked:
        return share_not_found(
            request,
            detail="Share link has been revoked",
            title="Link Revoked",
            message="This share link has been revoked by its owner.",
            headers=_SHARE_RESPONSE_HEADERS,
        )
    return None


@public_router.api_route("/{token}", methods=["GET", "POST"], response_model=None)
@limiter.limit("30/minute")
async def get_public_artifact_share(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
    workspace_root: str = Depends(get_workspace_root),
    password: str | None = Depends(resolve_gate_password),
) -> Response:
    """Serve the bundle entry file for a valid share token (no API key).

    GET also accepts a ``p`` query parameter so links carrying the password in
    the URL still unlock; POST reads the password from the form body (CWE-598)
    and answers with a 303 See Other redirect (PRG) so the password never
    appears in the address bar or browser history. When the share is too close
    to expiry to issue an unlock cookie the content is served directly instead
    of redirecting, so a successful unlock can never loop back to the gate.
    Revocation is checked before authentication so a revoked link (password
    protected or not) is denied immediately without presenting the gate.
    """
    revoked_response = await _ensure_not_revoked(db, token, request)
    if revoked_response is not None:
        return revoked_response
    result = _auth_or_gate(request, token, password)
    if isinstance(result, HTMLResponse):
        return result
    secure = request.url.scheme == "https"
    if request.method == "POST":
        redirect_path = str(request.url.path)
        if bundle_asset_count(result) > 1 and not redirect_path.endswith("/"):
            redirect_path += "/"
        response = RedirectResponse(url=redirect_path, status_code=303)
        if _attach_unlock_cookie(response, result, token, password, secure=secure):
            return response
        return await _serve_share_bundle(result, db, workspace_root, None, request)
    if bundle_asset_count(result) > 1 and not str(request.url.path).endswith("/"):
        redirect_url = str(request.url.replace(path=str(request.url.path) + "/"))
        response = RedirectResponse(url=redirect_url, status_code=307)
        _attach_unlock_cookie(response, result, token, password, secure=secure)
        return response
    response = await _serve_share_bundle(result, db, workspace_root, None, request)
    _attach_unlock_cookie(response, result, token, password, secure=secure)
    return response


@public_router.api_route("/{token}/", methods=["GET", "POST"])
@limiter.limit("30/minute")
async def get_public_artifact_share_index(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
    workspace_root: str = Depends(get_workspace_root),
    password: str | None = Depends(resolve_gate_password),
) -> Response:
    """Serve bundle entry under a trailing slash so relative static assets resolve."""
    revoked_response = await _ensure_not_revoked(db, token, request)
    if revoked_response is not None:
        return revoked_response
    result = _auth_or_gate(request, token, password)
    if isinstance(result, HTMLResponse):
        return result
    if request.method == "POST":
        response = RedirectResponse(url=str(request.url.path), status_code=303)
        if _attach_unlock_cookie(
            response, result, token, password, secure=request.url.scheme == "https"
        ):
            return response
        return await _serve_share_bundle(result, db, workspace_root, None, request)
    response = await _serve_share_bundle(result, db, workspace_root, None, request)
    _attach_unlock_cookie(
        response, result, token, password, secure=request.url.scheme == "https"
    )
    return response


@public_router.api_route("/{token}/{asset_path:path}", methods=["GET", "POST"])
@limiter.limit("60/minute")
async def get_public_artifact_share_asset(
    request: Request,
    token: str,
    asset_path: str,
    db: AsyncSession = Depends(get_db),
    workspace_root: str = Depends(get_workspace_root),
    password: str | None = Depends(resolve_gate_password),
) -> Response:
    """Serve a static asset from a multi-file share bundle."""
    revoked_response = await _ensure_not_revoked(db, token, request)
    if revoked_response is not None:
        return revoked_response
    result = _auth_or_gate(request, token, password)
    if isinstance(result, HTMLResponse):
        return result
    if request.method == "POST":
        response = RedirectResponse(url=str(request.url.path), status_code=303)
        if _attach_unlock_cookie(
            response, result, token, password, secure=request.url.scheme == "https"
        ):
            return response
        return await _serve_share_bundle(result, db, workspace_root, asset_path, request)
    return await _serve_share_bundle(result, db, workspace_root, asset_path, request)
