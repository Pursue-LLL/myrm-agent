"""Read-only public artifact share links (signed URLs).

[INPUT]
- app.services.artifacts.share_token (POS: HMAC token create/parse)
- app.services.artifacts.share_resolve (POS: vault path resolution)

[OUTPUT]
- router: authenticated create-share endpoints
- public_router: unauthenticated inline file view

[POS]
Lets GUI users share html/pdf/document artifacts without Vercel deploy.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_workspace_root
from app.core.infra.limiter import limiter
from app.config.settings import settings
from app.database.connection import get_db
from app.database.models.artifact import Artifact
from app.services.artifacts.share_resolve import resolve_shareable_version
from app.services.artifacts.share_token import (
    create_artifact_share_token,
    is_shareable_artifact_name,
    parse_artifact_share_token,
)

logger = logging.getLogger(__name__)

router = APIRouter()
public_router = APIRouter()

_MAX_TTL_DAYS = 30
_DEFAULT_TTL_DAYS = 7


class CreateArtifactShareRequest(BaseModel):
    ttl_days: int = Field(default=_DEFAULT_TTL_DAYS, ge=1, le=_MAX_TTL_DAYS)


class CreateArtifactShareResponse(BaseModel):
    token: str
    share_path: str
    expires_at: int
    artifact_id: str
    version_id: str


def _share_path(token: str) -> str:
    return f"/api/v1/public/artifact-share/{token}"


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
    if not is_shareable_artifact_name(artifact.name):
        raise HTTPException(
            status_code=400,
            detail="Only HTML, PDF, and document artifacts can use read-only share links.",
        )
    if not artifact.versions:
        raise HTTPException(status_code=400, detail="Artifact has no versions to share")

    latest = sorted(artifact.versions, key=lambda v: v.created_at, reverse=True)[0]
    try:
        await resolve_shareable_version(db, artifact.id, latest.id, workspace_root)
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (LookupError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    ttl_seconds = body.ttl_days * 24 * 3600
    token, expires_at = create_artifact_share_token(
        artifact.id,
        latest.id,
        ttl_seconds=ttl_seconds,
    )
    return CreateArtifactShareResponse(
        token=token,
        share_path=_share_path(token),
        expires_at=expires_at,
        artifact_id=artifact.id,
        version_id=latest.id,
    )


@public_router.get("/{token}")
async def get_public_artifact_share(
    token: str,
    db: AsyncSession = Depends(get_db),
    workspace_root: str = Depends(get_workspace_root),
) -> FileResponse:
    """Serve artifact bytes for a valid share token (no API key)."""
    claims = parse_artifact_share_token(token)
    if claims is None:
        raise HTTPException(status_code=404, detail="Share link is invalid or expired")

    try:
        content = await resolve_shareable_version(
            db,
            claims.artifact_id,
            claims.version_id,
            workspace_root,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError:
        raise HTTPException(status_code=404, detail="Artifact not found") from None
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Artifact content not found") from None
    except Exception as exc:
        logger.error("Public share resolve failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load shared artifact") from exc

    return FileResponse(
        path=str(content.path),
        media_type=content.media_type,
        filename=content.filename,
        content_disposition_type="inline",
    )
