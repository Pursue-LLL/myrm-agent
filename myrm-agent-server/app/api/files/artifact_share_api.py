"""Authenticated artifact share-link lifecycle (create / list / revoke).

[INPUT]
- app.services.artifacts.share.share_token (POS: HMAC token rebuild + shareability checks)
- app.services.artifacts.share.share_create (POS: sign + snapshot bundle + register one link, shared with IM buttons)
- app.services.artifacts.share.share_registry (POS: share-link lifecycle registry)
- app.database.models.artifact::Artifact (POS: artifact + versions metadata)
- app.core.infra.ingress::resolve_public_link_base (POS: public base of links opened elsewhere: running tunnel, else ingress)
- app.core.security.share.share_links (POS: where each share token kind is served)
- app.api.files.artifact_share_public::public_router (POS: unauthenticated serving)

[OUTPUT]
- router: authenticated create/list/revoke share endpoints
- public_router (re-export): unauthenticated inline file view

[POS]
Server business layer. Lets GUI users share html/pdf/document artifacts without
Vercel deploy, list active links, and revoke them immediately. Registration is
committed before the token is returned so every issued token is revocable. The
list endpoint rebuilds each unprotected share path on the fly (deterministic
HMAC tokens) so links are displayable/copyable without persisting raw tokens;
password-protected rows carry a persisted ``share_path`` (their token cannot be
rebuilt because the password is never stored). Create and list responses also
carry an absolute ``share_url`` derived from the shared public link base
(``resolve_public_link_base``: running tunnel, else public ingress) so links stay
reachable outside the local host in hosted/tunneled deployments (falls back to
``None`` so the frontend assembles from origin when neither exists).
"""

from __future__ import annotations

from calendar import timegm

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_workspace_root
from app.core.infra.ingress import resolve_public_link_base
from app.core.security.share.share_links import ShareKind, share_link_path
from app.database.connection import get_db
from app.database.models.artifact import Artifact
from app.services.artifacts.share.share_create import ShareRegistrationError, create_artifact_share
from app.services.artifacts.share.share_registry import (
    ActiveShareRow,
    list_active_shares,
    revoke_share,
)
from app.services.artifacts.share.share_token import is_shareable_artifact, rebuild_artifact_share_token

from .artifact_share_public import public_router as public_router

router = APIRouter()

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
    share_url: str | None = None
    expires_at: int
    artifact_id: str
    version_id: str
    password_protected: bool = False


class ArtifactShareRecordResponse(BaseModel):
    id: str
    artifact_id: str
    artifact_name: str
    artifact_type: str | None = None
    password_protected: bool = False
    created_at: int
    expires_at: int
    share_path: str | None = None
    share_url: str | None = None


def _absolute_share_url(base: str, share_path: str | None) -> str | None:
    """Prepend the public base to a relative share path when both exist."""
    if not base or not share_path:
        return None
    return f"{base}{share_path}"


def _record_share_path(row: ActiveShareRow) -> str | None:
    """Return the share URL path for a registry row.

    Password-protected tokens cannot be reconstructed because the password is
    never persisted, so their ``share_path`` is read from the stored column.
    Unprotected rows stay stateless and are rebuilt on the fly (deterministic
    HMAC tokens).
    """
    if row.share_path:
        return row.share_path
    if row.password_protected:
        return None
    token = rebuild_artifact_share_token(
        row.artifact_id,
        row.version_id,
        expires_at_unix=timegm(row.expires_at.timetuple()),
        artifact_type=row.artifact_type,
    )
    return share_link_path(ShareKind.ARTIFACT, token)


@router.post("/{artifact_id}/share-preview", response_model=CreateArtifactShareResponse)
async def create_artifact_share_preview(
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
    try:
        created = await create_artifact_share(
            db,
            workspace_root,
            artifact_id=artifact.id,
            version_id=latest.id,
            artifact_type=share_type,
            ttl_seconds=body.ttl_days * 24 * 3600,
            password=body.password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Artifact content not found") from exc
    except ShareRegistrationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    share_path = share_link_path(ShareKind.ARTIFACT, created.token)
    base = await resolve_public_link_base()
    return CreateArtifactShareResponse(
        token=created.token,
        share_path=share_path,
        share_url=_absolute_share_url(base, share_path),
        expires_at=created.expires_at,
        artifact_id=artifact.id,
        version_id=latest.id,
        password_protected=body.password is not None,
    )


def _record_response(row: ActiveShareRow, base: str) -> ArtifactShareRecordResponse:
    share_path = _record_share_path(row)
    return ArtifactShareRecordResponse(
        id=row.id,
        artifact_id=row.artifact_id,
        artifact_name=row.artifact_name,
        artifact_type=row.artifact_type,
        password_protected=row.password_protected,
        created_at=timegm(row.created_at.timetuple()),
        expires_at=timegm(row.expires_at.timetuple()),
        share_path=share_path,
        share_url=_absolute_share_url(base, share_path),
    )


@router.get("/shares", response_model=list[ArtifactShareRecordResponse])
async def get_artifact_share_records(
    db: AsyncSession = Depends(get_db),
) -> list[ArtifactShareRecordResponse]:
    """List unrevoked, unexpired share links for the management GUI (read-only)."""
    rows = await list_active_shares(db)
    base = await resolve_public_link_base()
    return [_record_response(row, base) for row in rows]


@router.delete("/shares/{record_id}", status_code=204)
async def delete_artifact_share_record(
    record_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Revoke a share link by registry id. Idempotent (204 on repeat).

    Purge of expired registry rows is owned by the periodic scheduler
    (``app.lifecycle.schedulers``), keeping this endpoint free of side effects
    beyond revocation itself.
    """
    if not await revoke_share(db, record_id):
        raise HTTPException(status_code=404, detail="Share link not found")
    return Response(status_code=204)
