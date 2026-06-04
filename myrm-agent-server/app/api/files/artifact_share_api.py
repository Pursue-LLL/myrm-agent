"""Read-only public artifact share links (signed URLs).

[INPUT]
- app.services.artifacts.share_token (POS: HMAC token create/parse)
- app.services.artifacts.share_bundle (POS: multi-file static bundle materialization)

[OUTPUT]
- router: authenticated create-share endpoints
- public_router: unauthenticated inline file view (entry + static assets)

[POS]
Lets GUI users share html/pdf/document artifacts without Vercel deploy.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_workspace_root
from app.config.settings import settings
from app.core.infra.limiter import limiter
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


class CreateArtifactShareResponse(BaseModel):
    token: str
    share_path: str
    expires_at: int
    artifact_id: str
    version_id: str


def _share_path(token: str) -> str:
    return f"/api/v1/public/artifact-share/{token}"


def _file_response(path: str, media_type: str, filename: str) -> FileResponse:
    return FileResponse(
        path=path,
        media_type=media_type,
        filename=filename,
        content_disposition_type="inline",
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
            raise HTTPException(status_code=404, detail="Artifact content not found") from exc
        except Exception as exc:
            logger.error("Share bundle materialize failed: %s", exc)
            raise HTTPException(status_code=500, detail="Failed to load shared artifact") from exc
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
        raise HTTPException(status_code=404, detail="Artifact content not found") from exc

    return CreateArtifactShareResponse(
        token=token,
        share_path=_share_path(token),
        expires_at=expires_at,
        artifact_id=artifact.id,
        version_id=latest.id,
    )


@public_router.get("/{token}", response_model=None)
async def get_public_artifact_share(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
    workspace_root: str = Depends(get_workspace_root),
):
    """Serve the bundle entry file for a valid share token (no API key)."""
    claims = parse_artifact_share_token(token)
    if claims is None:
        raise HTTPException(status_code=404, detail="Share link is invalid or expired")
    if bundle_asset_count(claims) > 1 and not str(request.url.path).endswith("/"):
        return RedirectResponse(url=str(request.url) + "/", status_code=307)
    return await _serve_share_bundle(claims, db, workspace_root, None)


@public_router.get("/{token}/")
async def get_public_artifact_share_index(
    token: str,
    db: AsyncSession = Depends(get_db),
    workspace_root: str = Depends(get_workspace_root),
) -> FileResponse:
    """Serve bundle entry under a trailing slash so relative static assets resolve."""
    claims = parse_artifact_share_token(token)
    if claims is None:
        raise HTTPException(status_code=404, detail="Share link is invalid or expired")
    return await _serve_share_bundle(claims, db, workspace_root, None)


@public_router.get("/{token}/{asset_path:path}")
async def get_public_artifact_share_asset(
    token: str,
    asset_path: str,
    db: AsyncSession = Depends(get_db),
    workspace_root: str = Depends(get_workspace_root),
) -> FileResponse:
    """Serve a static asset from a multi-file share bundle."""
    claims = parse_artifact_share_token(token)
    if claims is None:
        raise HTTPException(status_code=404, detail="Share link is invalid or expired")
    return await _serve_share_bundle(claims, db, workspace_root, asset_path)
