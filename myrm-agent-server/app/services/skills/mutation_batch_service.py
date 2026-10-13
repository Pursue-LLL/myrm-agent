"""Rollback skill_manage mutation batches stored in batch_snapshots."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import BatchSnapshot
from myrm_agent_harness.agent.skills.market.sanitizer import SKILL_MD_FILE

logger = logging.getLogger(__name__)


class MutationBatchRollbackError(ValueError):
    """Fail-closed rollback error."""


class MutationBatchCompensationError(MutationBatchRollbackError):
    """Rollback failed and restoring the pre-rollback live state also failed."""


class MutationBatchAlreadyConsumedError(MutationBatchRollbackError):
    """Batch snapshots are missing (unknown batch_id or rollback already applied)."""


_ROLLBACK_BATCH_KINDS = frozenset({"skill_mutation", "market_replace"})


@dataclass
class _SkillLiveState:
    skill_id: str
    skill_md: str | None
    resources: dict[str, str | None]
    skill_existed: bool


async def _read_skill_md(skill_id: str) -> str | None:
    from app.core.skills.store.service import skills_service

    raw = await skills_service.get_skill_file(skill_id, SKILL_MD_FILE)
    if raw is None:
        return None
    return raw.decode("utf-8") if isinstance(raw, bytes) else raw


async def _read_resource(skill_id: str, path: str) -> str | None:
    from app.core.skills.store.service import skills_service

    raw = await skills_service.get_skill_file(skill_id, path)
    if raw is None:
        return None
    return raw.decode("utf-8") if isinstance(raw, bytes) else raw


async def _capture_live_state(skill_id: str, resource_paths: set[str]) -> _SkillLiveState:
    from app.core.skills.store.service import skills_service

    skill = await skills_service.get_skill(skill_id)
    if not skill:
        return _SkillLiveState(
            skill_id=skill_id,
            skill_md=None,
            resources={path: None for path in resource_paths},
            skill_existed=False,
        )
    resources: dict[str, str | None] = {}
    for path in sorted(resource_paths):
        resources[path] = await _read_resource(skill_id, path)
    return _SkillLiveState(
        skill_id=skill_id,
        skill_md=await _read_skill_md(skill_id),
        resources=resources,
        skill_existed=True,
    )


async def _delete_skill_resource_file(skill_id: str, path: str) -> None:
    from pathlib import Path

    from app.core.skills.models import SkillType
    from app.core.skills.store.service import skills_service

    skill = await skills_service.get_skill(skill_id)
    if not skill:
        raise MutationBatchRollbackError(f"Skill not found: {skill_id}.")

    if ".." in path or path.startswith(("/", "\\")):
        raise MutationBatchRollbackError(f"Invalid resource path: {path}.")

    if skill.type == SkillType.LOCAL:
        base_dir = Path(skill.storage_path).resolve()
        target = (base_dir / path).resolve()
        if not target.is_relative_to(base_dir):
            raise MutationBatchRollbackError(f"Invalid resource path: {path}.")
        if target.is_file():
            target.unlink()
        return

    storage_key = f"{skill.storage_path}/{path}"
    if await skills_service.storage.exists(storage_key):
        await skills_service.storage.delete(storage_key)


async def _restore_live_state(state: _SkillLiveState) -> None:
    from app.core.skills.store.service import skills_service
    from app.services.skills.write_orchestrator import orchestrate_skill_file_write

    if not state.skill_existed:
        return

    if state.skill_md is None or not state.skill_md.strip():
        await skills_service.delete_skill(state.skill_id)
        return

    await orchestrate_skill_file_write(
        state.skill_id,
        SKILL_MD_FILE,
        state.skill_md,
        created_by="mutation_rollback",
    )

    for path, content in state.resources.items():
        if content is None:
            await _delete_skill_resource_file(state.skill_id, path)
        else:
            await orchestrate_skill_file_write(
                state.skill_id,
                path,
                content,
                created_by="mutation_rollback",
            )


async def _apply_row_snapshot(row: BatchSnapshot) -> None:
    from app.core.skills.store.service import skills_service
    from app.services.skills.write_orchestrator import orchestrate_skill_file_write

    meta = row.skill_metadata or {}
    content = row.skill_content_before or ""
    existed_before = bool(meta.get("existed_before_batch"))

    if not content.strip():
        if existed_before:
            raise MutationBatchRollbackError(
                f"Missing SKILL.md snapshot for skill_id={row.skill_id}; rollback aborted."
            )
        ok = await skills_service.delete_skill(row.skill_id)
        if not ok:
            raise MutationBatchRollbackError(
                f"Failed to remove skill created in batch (skill_id={row.skill_id})."
            )
        return

    await orchestrate_skill_file_write(
        row.skill_id,
        SKILL_MD_FILE,
        content,
        created_by="mutation_rollback",
    )

    resources = meta.get("resource_files") or {}
    if not isinstance(resources, dict):
        raise MutationBatchRollbackError(f"Invalid resource_files metadata for {row.skill_id}.")

    for path, file_content in resources.items():
        if not isinstance(path, str):
            continue
        if file_content is None:
            await _delete_skill_resource_file(row.skill_id, path)
            continue
        if not isinstance(file_content, str):
            raise MutationBatchRollbackError(f"Invalid resource blob for {path}.")
        await orchestrate_skill_file_write(
            row.skill_id,
            path,
            file_content,
            created_by="mutation_rollback",
        )


async def rollback_skill_mutation_batch(session: AsyncSession, batch_id: str) -> int:
    """Restore skills captured for a rollback-eligible batch snapshot. Returns skills restored."""
    result = await session.execute(select(BatchSnapshot).where(BatchSnapshot.batch_id == batch_id))
    rows = list(result.scalars().all())
    if not rows:
        raise MutationBatchAlreadyConsumedError(
            f"No rollback snapshots for batch_id={batch_id} (unknown id or already undone)."
        )

    batch_kind: str | None = None
    for row in rows:
        meta = row.skill_metadata or {}
        kind = meta.get("batch_kind")
        if not isinstance(kind, str):
            raise MutationBatchRollbackError(
                f"Batch {batch_id} has invalid batch_kind metadata (skill_id={row.skill_id})."
            )
        if kind not in _ROLLBACK_BATCH_KINDS:
            raise MutationBatchRollbackError(
                f"Batch {batch_id} is not rollback-eligible (batch_kind={kind}, skill_id={row.skill_id})."
            )
        if batch_kind is None:
            batch_kind = kind
        elif batch_kind != kind:
            raise MutationBatchRollbackError(f"Batch {batch_id} mixes incompatible batch_kind values.")

    live_by_id: dict[str, _SkillLiveState] = {}
    for row in rows:
        meta = row.skill_metadata or {}
        resources = meta.get("resource_files") or {}
        paths: set[str] = set()
        if isinstance(resources, dict):
            paths = {p for p in resources if isinstance(p, str)}
        if row.skill_id not in live_by_id:
            live_by_id[row.skill_id] = await _capture_live_state(row.skill_id, paths)

    applied_ids: list[str] = []
    current_skill_id: str | None = None
    try:
        for row in rows:
            current_skill_id = row.skill_id
            await _apply_row_snapshot(row)
            applied_ids.append(row.skill_id)
    except Exception as exc:
        compensation_failed = False
        for sid in reversed(applied_ids):
            try:
                await _restore_live_state(live_by_id[sid])
            except Exception as comp_exc:
                compensation_failed = True
                logger.error(
                    "Compensation failed for skill %s during batch %s rollback: %s",
                    sid,
                    batch_id,
                    comp_exc,
                )
        if current_skill_id is not None and current_skill_id not in applied_ids:
            try:
                await _restore_live_state(live_by_id[current_skill_id])
            except Exception as comp_exc:
                compensation_failed = True
                logger.error(
                    "Compensation failed for partial skill %s during batch %s rollback: %s",
                    current_skill_id,
                    batch_id,
                    comp_exc,
                )
        if compensation_failed:
            raise MutationBatchCompensationError(
                "Rollback could not be completed safely; check skill versions in Settings."
            ) from exc
        if isinstance(exc, MutationBatchRollbackError):
            raise
        raise MutationBatchRollbackError(f"Batch rollback failed for batch_id={batch_id}.") from exc

    from app.core.skills.config_version import bump_skill_config_version

    bump_skill_config_version()
    await session.execute(delete(BatchSnapshot).where(BatchSnapshot.batch_id == batch_id))
    restored = len(applied_ids)
    logger.info("Rolled back %s batch %s (%s skills)", batch_kind or "snapshot", batch_id, restored)
    return restored
