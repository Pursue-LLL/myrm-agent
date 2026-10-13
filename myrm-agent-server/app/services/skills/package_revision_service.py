"""Package revision persistence and restore.

[INPUT]
- app.database.models.skill_optimization.skill_package_revision::SkillPackageRevision (POS: revision rows)
- app.core.skills.store.service::skills_service (POS: SKILL.md and resource-file writes during restore)

[OUTPUT]
- capture_package_revision / list_package_revisions / restore_package_revision
- PackageRevisionSummary, PackageRevisionRestoreError

[POS]
Business service behind the skill version routes: stores full package snapshots and restores them fail-closed.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from myrm_agent_harness.agent.skills.market.sanitizer import SKILL_MD_FILE
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.skill_optimization.skill_package_revision import SkillPackageRevision

logger = logging.getLogger(__name__)


class PackageRevisionRestoreError(ValueError):
    """Raised when a package revision cannot be restored fail-closed."""


@dataclass(frozen=True)
class PackageRevisionSummary:
    revision_number: int
    revision_id: str
    created_by: str
    resource_paths: list[str]


async def _next_revision_number(session: AsyncSession, skill_id: str) -> int:
    result = await session.execute(
        select(func.max(SkillPackageRevision.revision_number)).where(SkillPackageRevision.skill_id == skill_id)
    )
    current = result.scalar_one_or_none()
    return int(current or 0) + 1


async def capture_package_revision(
    session: AsyncSession,
    skill_id: str,
    *,
    created_by: str,
    skill_md: str,
    resource_files: dict[str, str | None],
) -> SkillPackageRevision:
    """Store a full package snapshot."""
    revision_number = await _next_revision_number(session, skill_id)
    row = SkillPackageRevision(
        revision_id=str(uuid.uuid4()),
        skill_id=skill_id,
        revision_number=revision_number,
        created_by=created_by,
        skill_md=skill_md,
        resource_files=resource_files,
    )
    session.add(row)
    await session.flush()
    return row


async def list_package_revisions(
    session: AsyncSession,
    skill_id: str,
    *,
    limit: int = 50,
) -> list[PackageRevisionSummary]:
    result = await session.execute(
        select(SkillPackageRevision)
        .where(SkillPackageRevision.skill_id == skill_id)
        .order_by(SkillPackageRevision.revision_number.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        PackageRevisionSummary(
            revision_number=r.revision_number,
            revision_id=r.revision_id,
            created_by=r.created_by,
            resource_paths=sorted(r.resource_files.keys()),
        )
        for r in rows
    ]


async def restore_package_revision(
    session: AsyncSession,
    skill_id: str,
    revision_number: int,
) -> None:
    """Fail-closed restore of SKILL.md and all resource files from a revision."""
    from app.core.skills.store.service import skills_service

    result = await session.execute(
        select(SkillPackageRevision).where(
            SkillPackageRevision.skill_id == skill_id,
            SkillPackageRevision.revision_number == revision_number,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise PackageRevisionRestoreError(f"Revision {revision_number} not found for skill {skill_id}.")

    if not row.skill_md.strip():
        raise PackageRevisionRestoreError("Revision SKILL.md content is missing; restore aborted.")

    updated = await skills_service.update_skill_file(skill_id, SKILL_MD_FILE, row.skill_md)
    if not updated:
        raise PackageRevisionRestoreError("Failed to write SKILL.md during restore.")

    for path, content in row.resource_files.items():
        if content is None:
            continue
        ok = await skills_service.update_skill_file(skill_id, path, content)
        if not ok:
            raise PackageRevisionRestoreError(f"Failed to restore resource '{path}'.")

    logger.info("Restored skill %s to package revision %s", skill_id, revision_number)
