"""Persist and query artifact publication rows.

[POS] ORM-backed store for per-artifact, per-target publication history.

[INPUT]
- sqlalchemy (POS: async DB session)

[OUTPUT]
- CRUD helpers for ArtifactPublication rows and latest-status lookup
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.artifact_publication import ArtifactPublication


async def get_publication(
    db: AsyncSession,
    artifact_id: str,
    hosting_target_id: str,
) -> ArtifactPublication | None:
    return (
        await db.execute(
            select(ArtifactPublication).where(
                ArtifactPublication.artifact_id == artifact_id,
                ArtifactPublication.hosting_target_id == hosting_target_id,
            )
        )
    ).scalars().first()


async def list_publications(db: AsyncSession, artifact_id: str) -> list[ArtifactPublication]:
    return list(
        (
            await db.execute(
                select(ArtifactPublication)
                .where(ArtifactPublication.artifact_id == artifact_id)
                .order_by(ArtifactPublication.updated_at.desc())
            )
        ).scalars().all()
    )


async def list_publications_for_artifacts(
    db: AsyncSession,
    artifact_ids: list[str],
) -> dict[str, list[ArtifactPublication]]:
    if not artifact_ids:
        return {}
    rows = list(
        (
            await db.execute(
                select(ArtifactPublication)
                .where(ArtifactPublication.artifact_id.in_(artifact_ids))
                .order_by(ArtifactPublication.updated_at.desc())
            )
        ).scalars().all()
    )
    grouped: dict[str, list[ArtifactPublication]] = {artifact_id: [] for artifact_id in artifact_ids}
    for row in rows:
        grouped.setdefault(row.artifact_id, []).append(row)
    return grouped


async def upsert_publication(
    db: AsyncSession,
    *,
    artifact_id: str,
    hosting_target_id: str,
    publication_url: str | None,
    publication_status: str,
    publication_project_ref: str | None,
    publication_version_id: str | None,
) -> ArtifactPublication:
    row = await get_publication(db, artifact_id, hosting_target_id)
    if row is None:
        row = ArtifactPublication(
            id=str(uuid.uuid4()),
            artifact_id=artifact_id,
            hosting_target_id=hosting_target_id,
        )
        db.add(row)
    row.publication_url = publication_url
    row.publication_status = publication_status
    row.publication_project_ref = publication_project_ref
    row.publication_version_id = publication_version_id
    await db.commit()
    await db.refresh(row)
    return row


def publication_to_dict(
    row: ArtifactPublication,
    *,
    hosting_target_name: str | None = None,
) -> dict[str, str | None]:
    return {
        "id": row.id,
        "hosting_target_id": row.hosting_target_id,
        "hosting_target_name": hosting_target_name,
        "publication_url": row.publication_url,
        "publication_status": row.publication_status,
        "publication_project_ref": row.publication_project_ref,
        "publication_version_id": row.publication_version_id,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
