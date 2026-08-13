"""Unauthenticated public endpoint for artifact share bundles (entry + assets).

[INPUT]
- app.core.security.share_hmac (POS: HMAC signing + password-protection detection)
- app.core.security.share_password_page (POS: password gate HTML rendering)
- app.services.artifacts.share_bundle (POS: multi-file static bundle materialization)
- app.services.artifacts.share_registry (POS: revocation gate check)
- app.services.artifacts.share_token::ArtifactShareClaims (POS: HMAC claims)

[OUTPUT]
- public_router: unauthenticated inline file view (entry + static assets)

[POS]
Server business layer. Serves materialized share bundles to the public web with
hardened CSP headers, optional password gate, and a manual-revocation gate that
blocks both existing files and any re-materialization attempt after revoke.
"""

from __future__ import annotations

import hashlib
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_workspace_root
from app.core.infra.limiter import limiter
from app.core.security.share_hmac import (
    create_share_token,
    is_password_protected,
    parse_share_token,
)
from app.core.security.share_password_page import render_password_gate_html
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

_UNLOCK_COOKIE_NAME = "artifact_share_unlock"
_UNLOCK_SALT = "artifact-share-unlock"
_UNLOCK_COOKIE_PATH = "/api/v1/public/artifact-share"


def _file_response(path: str, media_type: str, filename: str) -> FileResponse:
    headers = _SHARE_SECURITY_HEADERS if media_type in _HTML_MEDIA_TYPES else None
    return FileResponse(
        path=path,
        headers=headers,
        media_type=media_type,
        filename=filename,
        content_disposition_type="inline",
    )


def _unlock_cookie_name(token: str) -> str:
    """Per-share cookie name so concurrent password shares never collide.

    A single fixed cookie name would be overwritten when a user opens several
    password-protected shares, causing later asset requests to authorize against
    the wrong share's credentials.
    """
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    return f"{_UNLOCK_COOKIE_NAME}_{digest}"


def _build_unlock_credential(claims: ArtifactShareClaims) -> str | None:
    """Issue a short-lived credential after a correct password unlock.

    Stateless HMAC token that carries the same artifact identity and expiry as
    the share token, so static-asset requests (which cannot carry the password)
    are authorized without re-entering it.
    """
    remaining = claims.exp - int(time.time())
    if remaining < 60:
        return None
    credential, _ = create_share_token(
        {"aid": claims.artifact_id, "vid": claims.version_id, "exp": claims.exp},
        salt=_UNLOCK_SALT,
        ttl_seconds=remaining,
        max_ttl_seconds=30 * 24 * 3600,
    )
    return credential


def _unlock_claims_from_cookie(value: str) -> ArtifactShareClaims | None:
    """Recover share claims from a signed unlock credential, or ``None``."""
    parsed = parse_share_token(value, salt=_UNLOCK_SALT)
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
    return ArtifactShareClaims(artifact_id=artifact_id, version_id=version_id, exp=exp)


def _attach_unlock_cookie(
    response: Response,
    claims: ArtifactShareClaims,
    token: str,
    password: str | None,
    *,
    secure: bool,
) -> None:
    if not password:
        return
    credential = _build_unlock_credential(claims)
    if credential is None:
        return
    response.set_cookie(
        key=_unlock_cookie_name(token),
        value=credential,
        max_age=max(0, claims.exp - int(time.time())),
        path=_UNLOCK_COOKIE_PATH,
        httponly=True,
        samesite="strict",
        secure=secure,
    )


async def _serve_share_bundle(
    claims: ArtifactShareClaims,
    db: AsyncSession,
    workspace_root: str,
    relative_path: str | None,
) -> FileResponse:
    purge_expired_share_bundles()
    resolved = resolve_share_bundle_file(claims, relative_path)
    if resolved is None:
        try:
            await materialize_share_bundle(db, workspace_root, claims)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail="Artifact content not found"
            ) from exc
        except Exception as exc:
            logger.error("Share bundle materialize failed: %s", exc)
            raise HTTPException(
                status_code=500, detail="Failed to load shared artifact"
            ) from exc
        resolved = resolve_share_bundle_file(claims, relative_path)

    if resolved is None:
        raise HTTPException(status_code=404, detail="Shared file not found")

    file_path, media_type, filename = resolved
    return _file_response(str(file_path), media_type, filename)


def _auth_or_gate(
    request: Request,
    token: str,
    password: str | None,
) -> ArtifactShareClaims | HTMLResponse:
    """Authenticate a password-protected share using ``p`` or a prior unlock cookie.

    Returns ``ArtifactShareClaims`` on success, or a ``HTMLResponse`` password-gate
    page when a password is required but missing/wrong. The unlock cookie lets
    static-asset requests (which do not carry the password) pass once unlocked.
    """
    protected = is_password_protected(token)
    if protected and not password:
        unlock = request.cookies.get(_unlock_cookie_name(token))
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
        raise HTTPException(status_code=404, detail="Share link is invalid or expired")
    return claims


async def _ensure_not_revoked(db: AsyncSession, token: str) -> None:
    """Reject requests whose token has been manually revoked.

    Called before token authentication on every public entry so a revoked
    share (password-protected or not) is denied immediately without
    presenting the password gate or touching the on-disk bundle.
    """
    try:
        revoked = await is_token_revoked(db, token)
    except Exception as exc:
        logger.warning("Share revocation check failed: %s", exc)
        revoked = False
    if revoked:
        raise HTTPException(status_code=404, detail="Share link has been revoked")


@public_router.get("/{token}", response_model=None)
@limiter.limit("30/minute")
async def get_public_artifact_share(
    request: Request,
    token: str,
    pwd: str | None = Query(default=None, alias="p"),
    db: AsyncSession = Depends(get_db),
    workspace_root: str = Depends(get_workspace_root),
) -> Response:
    """Serve the bundle entry file for a valid share token (no API key).

    Revocation is checked before authentication so a revoked link (password
    protected or not) is denied immediately without presenting the password gate.
    """
    await _ensure_not_revoked(db, token)
    result = _auth_or_gate(request, token, pwd)
    if isinstance(result, HTMLResponse):
        return result
    secure = request.url.scheme == "https"
    if bundle_asset_count(result) > 1 and not str(request.url.path).endswith("/"):
        redirect_url = str(request.url.replace(path=str(request.url.path) + "/"))
        response = RedirectResponse(url=redirect_url, status_code=307)
        _attach_unlock_cookie(response, result, token, pwd, secure=secure)
        return response
    response = await _serve_share_bundle(result, db, workspace_root, None)
    _attach_unlock_cookie(response, result, token, pwd, secure=secure)
    return response


@public_router.get("/{token}/")
@limiter.limit("30/minute")
async def get_public_artifact_share_index(
    request: Request,
    token: str,
    pwd: str | None = Query(default=None, alias="p"),
    db: AsyncSession = Depends(get_db),
    workspace_root: str = Depends(get_workspace_root),
):
    """Serve bundle entry under a trailing slash so relative static assets resolve."""
    await _ensure_not_revoked(db, token)
    result = _auth_or_gate(request, token, pwd)
    if isinstance(result, HTMLResponse):
        return result
    response = await _serve_share_bundle(result, db, workspace_root, None)
    _attach_unlock_cookie(
        response, result, token, pwd, secure=request.url.scheme == "https"
    )
    return response


@public_router.get("/{token}/{asset_path:path}")
@limiter.limit("60/minute")
async def get_public_artifact_share_asset(
    request: Request,
    token: str,
    asset_path: str,
    pwd: str | None = Query(default=None, alias="p"),
    db: AsyncSession = Depends(get_db),
    workspace_root: str = Depends(get_workspace_root),
):
    """Serve a static asset from a multi-file share bundle."""
    await _ensure_not_revoked(db, token)
    result = _auth_or_gate(request, token, pwd)
    if isinstance(result, HTMLResponse):
        return result
    return await _serve_share_bundle(result, db, workspace_root, asset_path)
