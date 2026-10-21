"""Unified server-side skill file writes: disk + DB version snapshots (SSOT).

[INPUT]
- app.core.skills.store.service::skills_service (POS: skill file read/write)
- app.services.skill_optimization.skill_version_sync::persist_skill_version (POS: DB snapshot)

[OUTPUT]
- SkillFileWriteResult: outcome of orchestrated write
- orchestrate_skill_file_write: scan-adjacent persist path for API and meta-tool hooks
- note_skill_content_hash / skill_content_hashes_for_ids: execution-cache fingerprint inputs

[POS]
Single write orchestrator for SKILL.md (and other skill files). Version history SSOT is server DB.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from myrm_agent_harness.agent.skills.market.sanitizer import SKILL_MD_FILE
from myrm_agent_harness.api.skills import compute_content_hash

logger = logging.getLogger(__name__)

_CONTENT_HASH_REGISTRY: dict[str, str] = {}
_REGISTRY_LOCK = Lock()


class SkillContentConflictError(ValueError):
    """Raised when If-Match / content-hash CAS does not match on-disk content."""


@dataclass(frozen=True)
class SkillFileWriteResult:
    content_hash: str
    version_persisted: bool
    version_number: int | None = None
    skipped_unchanged: bool = False


def note_skill_content_hash(skill_id: str, content_hash: str) -> None:
    with _REGISTRY_LOCK:
        _CONTENT_HASH_REGISTRY[skill_id] = content_hash


def skill_content_hashes_for_ids(skill_ids: list[str]) -> dict[str, str]:
    with _REGISTRY_LOCK:
        return {sid: _CONTENT_HASH_REGISTRY[sid] for sid in sorted(skill_ids) if sid in _CONTENT_HASH_REGISTRY}


def _is_skill_md(filename: str) -> bool:
    return Path(filename).name == SKILL_MD_FILE


async def _read_current_text(skill_id: str, filename: str) -> str | None:
    from app.core.skills.store.service import skills_service

    raw = await skills_service.get_skill_file(skill_id, filename)
    if raw is None:
        return None
    return raw.decode("utf-8") if isinstance(raw, bytes) else raw


async def persist_skill_md_snapshot(
    skill_id: str,
    content: str,
    *,
    created_by: str,
    sync_disk: bool = False,
    disk_path: Path | None = None,
    optimization_id: str | None = None,
) -> tuple[bool, int | None]:
    """Persist DB version when SKILL.md content hash changed (idempotent)."""
    content_hash = compute_content_hash(content)
    note_skill_content_hash(skill_id, content_hash)

    from app.services.skill_optimization.bootstrap import get_skill_optimization_storage
    from app.services.skill_optimization.skill_version_sync import persist_skill_version

    storage = get_skill_optimization_storage()
    active = await storage.get_active_version(skill_id)
    if active is not None and compute_content_hash(active.content) == content_hash:
        return False, active.version

    saved = await persist_skill_version(
        storage,
        skill_id,
        content,
        created_by=created_by,
        optimization_id=optimization_id,
        sync_disk=sync_disk,
        disk_path=disk_path,
    )
    if not sync_disk:
        from app.core.skills.config_version import bump_skill_config_version

        bump_skill_config_version()
    return True, saved.version


async def orchestrate_skill_file_write(
    skill_id: str,
    filename: str,
    content: str,
    *,
    created_by: str,
    if_match: str | None = None,
) -> SkillFileWriteResult:
    """Write skill file to storage and snapshot SKILL.md versions when content changes."""
    from app.core.skills.config_version import bump_skill_config_version
    from app.core.skills.store.service import skills_service

    content_hash = compute_content_hash(content)
    is_md = _is_skill_md(filename)

    if is_md:
        prior = await _read_current_text(skill_id, filename)
        prior_hash = compute_content_hash(prior) if prior is not None else None
        if if_match is not None:
            expected = if_match.strip().strip('"')
            if prior_hash is None or prior_hash != expected:
                raise SkillContentConflictError("Skill file was modified elsewhere; refresh and retry (If-Match mismatch).")
        if prior_hash == content_hash:
            note_skill_content_hash(skill_id, content_hash)
            return SkillFileWriteResult(
                content_hash=content_hash,
                version_persisted=False,
                skipped_unchanged=True,
            )

    if is_md:
        persisted, version_number = await persist_skill_md_snapshot(
            skill_id,
            content,
            created_by=created_by,
            sync_disk=True,
        )
        return SkillFileWriteResult(
            content_hash=content_hash,
            version_persisted=persisted,
            version_number=version_number,
        )

    updated = await skills_service.update_skill_file(skill_id, filename, content)
    if not updated:
        raise RuntimeError(f"Failed to write {filename} for skill {skill_id}")

    bump_skill_config_version()
    return SkillFileWriteResult(content_hash=content_hash, version_persisted=False)


async def record_resource_package_revision(
    skill_id: str,
    resource_path: str,
    content: str,
    *,
    created_by: str,
) -> None:
    """Capture a package revision after a resource file was written."""
    from app.core.skills.config_version import bump_skill_config_version
    from app.services.skill_optimization.bootstrap import get_skill_optimization_storage
    from app.services.skills.package_revision_service import capture_package_revision

    skill_md = await _read_current_text(skill_id, SKILL_MD_FILE) or ""
    if not skill_md.strip():
        raise RuntimeError("SKILL.md missing after resource write; package revision aborted.")

    storage = get_skill_optimization_storage()
    async with storage._get_session() as session:
        await capture_package_revision(
            session,
            skill_id,
            created_by=created_by,
            skill_md=skill_md,
            resource_files={resource_path: content},
        )
        await session.commit()

    bump_skill_config_version()


async def restore_skill_md_from_active_version(skill_id: str) -> bool:
    """Rewrite on-disk SKILL.md from the active DB version (compensating rollback)."""
    from app.services.skill_optimization.bootstrap import get_skill_optimization_storage
    from app.services.skill_optimization.skill_version_sync import sync_content_to_disk

    storage = get_skill_optimization_storage()
    active = await storage.get_active_version(skill_id)
    if active is None:
        return False
    return await sync_content_to_disk(skill_id, active.content)


async def resolve_skill_id_by_name(skill_name: str) -> str | None:
    from app.core.skills.store.service import skills_service

    skills = await skills_service.list_skills()
    for skill in skills:
        if skill.name == skill_name:
            return skill.id
    return None
