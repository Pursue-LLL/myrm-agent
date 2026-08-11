"""Read-only public artifact share links (signed URLs).

[INPUT]
- app.services.artifacts.share_token (POS: HMAC token create/parse)
- app.services.artifacts.share_bundle (POS: multi-file static bundle materialization)
- app.core.security.share_hmac (POS: HMAC signing + password-protection detection)

[OUTPUT]
- router: authenticated create-share endpoints
- public_router: unauthenticated inline file view (entry + static assets)

[POS]
Lets GUI users share html/pdf/document artifacts without Vercel deploy.
Supports optional password-protected share links.
"""

from __future__ import annotations

import hashlib
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_workspace_root
from app.config.settings import settings
from app.core.infra.limiter import limiter
from app.core.security.share_hmac import (
    create_share_token,
    is_password_protected,
    parse_share_token,
)
from app.core.security.share_password_page import render_password_gate_html
from app.database.connection import get_db
from app.database.models.artifact import Artifact
from app.services.artifacts.share_bundle import (
    bundle_asset_count,
    materialize_share_bundle,
    purge_expired_share_bundles,
    resolve_share_bundle_file,
)
from app.services.artifacts.share_token import (
    ArtifactShareClaims,
    create_artifact_share_token,
    is_shareable_artifact,
    parse_artifact_share_token,
)

logger = logging.getLogger(__name__)

router = APIRouter()
public_router = APIRouter()

_MAX_TTL_DAYS = 30
_DEFAULT_TTL_DAYS = 7


class CreateArtifactShareRequest(BaseModel):
    ttl_days: int = Field(default=_DEFAULT_TTL_DAYS, ge=1, le=_MAX_TTL_DAYS)
    artifact_type: str | None = Field(
        default=None,
        description="Client artifact type from SSE (html, pdf, document) when DB name lacks suffix.",
    )
    password: str | None = Field(default=None, min_length=1, max_length=64)


class CreateArtifactShareResponse(BaseModel):
    token: str
    share_path: str
    expires_at: int
    artifact_id: str
    version_id: str
    password_protected: bool = False


def _share_path(token: str) -> str:
    return f"/api/v1/public/artifact-share/{token}"


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


def _file_response(path: str, media_type: str, filename: str) -> FileResponse:
    headers = _SHARE_SECURITY_HEADERS if media_type in _HTML_MEDIA_TYPES else None
    return FileResponse(
        path=path,
        headers=headers,
        media_type=media_type,
        filename=filename,
        content_disposition_type="inline",
    )


_UNLOCK_COOKIE_NAME = "artifact_share_unlock"
_UNLOCK_SALT = "artifact-share-unlock"
_UNLOCK_COOKIE_PATH = "/api/v1/public/artifact-share"


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


@router.post("/{artifact_id}/share-preview", response_model=CreateArtifactShareResponse)
@limiter.limit(settings.rate_limit.artifact_deploy)
async def create_artifact_share_preview(
    request: Request,
    artifact_id: str,
    body: CreateArtifactShareRequest,
    db: AsyncSession = Depends(get_db),
    workspace_root: str = Depends(get_workspace_root),
) -> CreateArtifactShareResponse:
    """Create a time-limited read-only link for shareable artifacts."""
    stmt = (
        select(Artifact)
        .options(selectinload(Artifact.versions))
        .where(Artifact.id == artifact_id, Artifact.is_deleted.is_(False))
    )
    artifact = (await db.execute(stmt)).scalars().first()
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    share_type = (body.artifact_type or "").strip().lower() or None
    if not is_shareable_artifact(artifact.name, share_type):
        raise HTTPException(
            status_code=400,
            detail="Only HTML, PDF, and document artifacts can use read-only share links.",
        )
    if not artifact.versions:
        raise HTTPException(status_code=400, detail="Artifact has no versions to share")

    latest = sorted(artifact.versions, key=lambda v: v.created_at, reverse=True)[0]
    ttl_seconds = body.ttl_days * 24 * 3600
    token, expires_at = create_artifact_share_token(
        artifact.id,
        latest.id,
        ttl_seconds=ttl_seconds,
        artifact_type=share_type,
        password=body.password,
    )
    claims = ArtifactShareClaims(
        artifact_id=artifact.id,
        version_id=latest.id,
        exp=expires_at,
        artifact_type=share_type,
    )
    try:
        await materialize_share_bundle(db, workspace_root, claims)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Artifact content not found"
        ) from exc

    return CreateArtifactShareResponse(
        token=token,
        share_path=_share_path(token),
        expires_at=expires_at,
        artifact_id=artifact.id,
        version_id=latest.id,
        password_protected=body.password is not None,
    )


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


@public_router.get("/{token}", response_model=None)
@limiter.limit("30/minute")
async def get_public_artifact_share(
    request: Request,
    token: str,
    pwd: str | None = Query(default=None, alias="p"),
    db: AsyncSession = Depends(get_db),
    workspace_root: str = Depends(get_workspace_root),
):
    """Serve the bundle entry file for a valid share token (no API key)."""
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
    result = _auth_or_gate(request, token, pwd)
    if isinstance(result, HTMLResponse):
        return result
    response = await _serve_share_bundle(result, db, workspace_root, None)
    _attach_unlock_cookie(response, result, token, pwd, secure=request.url.scheme == "https")
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
    result = _auth_or_gate(request, token, pwd)
    if isinstance(result, HTMLResponse):
        return result
    return await _serve_share_bundle(result, db, workspace_root, asset_path)
