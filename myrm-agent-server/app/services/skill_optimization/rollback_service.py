"""Batch Rollback Service

One-click rollback for batch optimization using snapshots.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import BatchSnapshot

logger = logging.getLogger(__name__)


@dataclass
class RollbackResult:
    """Rollback operation result

    Attributes:
        success: Whether rollback succeeded
        total_skills: Total number of skills to rollback
        rolled_back: Number of skills successfully rolled back
        failed: Number of skills that failed to rollback
        error_message: Error message if rollback failed
    """

    success: bool
    total_skills: int
    rolled_back: int
    failed: int
    error_message: str | None = None


@dataclass(frozen=True)
class _BatchSkillSnapshot:
    skill_id: str
    skill_content_before: str
    skill_version_before: int


class RollbackService:
    """Batch optimization rollback service"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _load_batch_snapshots(self, batch_id: str) -> list[_BatchSkillSnapshot]:
        result = await self.session.execute(select(BatchSnapshot).where(BatchSnapshot.batch_id == batch_id))
        rows = result.scalars().all()
        return [
            _BatchSkillSnapshot(
                skill_id=r.skill_id,
                skill_content_before=r.skill_content_before,
                skill_version_before=r.skill_version_before,
            )
            for r in rows
        ]

    async def _insert_batch_snapshot(
        self,
        batch_id: str,
        skill_id: str,
        skill_content: str,
        skill_version: int,
        metadata: dict[str, object],
    ) -> None:
        row = BatchSnapshot(
            snapshot_id=str(uuid.uuid4()),
            batch_id=batch_id,
            skill_id=skill_id,
            skill_content_before=skill_content,
            skill_version_before=skill_version,
            skill_metadata=metadata,
        )
        self.session.add(row)
        await self.session.commit()

    async def _delete_batch_snapshots(self, batch_id: str) -> int:
        result = await self.session.execute(select(BatchSnapshot).where(BatchSnapshot.batch_id == batch_id))
        rows = list(result.scalars().all())
        n = len(rows)
        if n:
            await self.session.execute(delete(BatchSnapshot).where(BatchSnapshot.batch_id == batch_id))
            await self.session.commit()
        return n

    async def rollback_batch(
        self,
        batch_id: str,
        skill_writer: Callable[[str, str, int], Awaitable[None]],
    ) -> RollbackResult:
        """Rollback batch optimization to snapshot state

        Args:
            batch_id: Batch task ID
            skill_writer: Async callable to write skill content (skill_id, content, version) -> None

        Returns:
            RollbackResult: Rollback operation result
        """
        snapshots = await self._load_batch_snapshots(batch_id)

        if not snapshots:
            error_msg = f"No snapshots found for batch {batch_id}"
            logger.error(error_msg)
            return RollbackResult(
                success=False,
                total_skills=0,
                rolled_back=0,
                failed=0,
                error_message=error_msg,
            )

        total = len(snapshots)
        rolled_back = 0
        failed = 0

        logger.info(f"Starting rollback for batch {batch_id}: {total} skills")

        for snapshot in snapshots:
            try:
                await skill_writer(
                    snapshot.skill_id,
                    snapshot.skill_content_before,
                    snapshot.skill_version_before,
                )
                rolled_back += 1
                logger.info(f"Rolled back skill {snapshot.skill_id} to version {snapshot.skill_version_before}")
            except Exception as e:
                failed += 1
                logger.error(f"Failed to rollback skill {snapshot.skill_id}: {e}")

        success = failed == 0

        if success:
            logger.info(f"Batch {batch_id} rollback completed: {rolled_back}/{total} skills restored")
        else:
            logger.warning(f"Batch {batch_id} rollback partially completed: {rolled_back} succeeded, {failed} failed")

        return RollbackResult(
            success=success,
            total_skills=total,
            rolled_back=rolled_back,
            failed=failed,
            error_message=None if success else f"{failed} skills failed to rollback",
        )

    async def create_batch_snapshot(
        self,
        batch_id: str,
        skill_ids: list[str],
        skill_reader: Callable[[str], Awaitable[tuple[str, int, dict[str, object]]]],
    ) -> bool:
        """Create snapshots for all skills before batch optimization

        Args:
            batch_id: Batch task ID
            skill_ids: List of skill IDs to snapshot
            skill_reader: Async callable to read skill (skill_id) -> (content, version, metadata)

        Returns:
            bool: Whether snapshot creation succeeded
        """
        logger.info(f"Creating snapshots for batch {batch_id}: {len(skill_ids)} skills")

        for skill_id in skill_ids:
            try:
                content, version, metadata = await skill_reader(skill_id)
                await self._insert_batch_snapshot(
                    batch_id=batch_id,
                    skill_id=skill_id,
                    skill_content=content,
                    skill_version=version,
                    metadata=metadata,
                )
            except Exception as e:
                logger.error(f"Failed to create snapshot for skill {skill_id}: {e}")
                return False

        logger.info(f"Successfully created {len(skill_ids)} snapshots for batch {batch_id}")
        return True

    async def delete_batch_snapshot(self, batch_id: str) -> int:
        """Delete batch snapshots (e.g., after confirmed success)

        Args:
            batch_id: Batch task ID

        Returns:
            int: Number of deleted snapshots
        """
        count = await self._delete_batch_snapshots(batch_id)
        logger.info(f"Deleted {count} snapshots for batch {batch_id}")
        return count
