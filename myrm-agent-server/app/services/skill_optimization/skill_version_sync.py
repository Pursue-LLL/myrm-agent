"""Skill version dual-write: DB snapshots synchronized with on-disk SKILL.md.

[INPUT]
- app.adapters.skill_optimization.sqlalchemy_storage::SQLAlchemyStorage (POS: SkillOptimizationStorage 协议适配器)
- app.core.skills.store.service::skills_service (POS: 技能增删改查服务)

[OUTPUT]
- persist_skill_version: 保存并可选激活 DB 快照（含重试与 .bak 失效）
- activate_version_with_disk_sync: 激活快照并同步磁盘
- restore_skill_snapshot: 批量/手动恢复到指定快照
- ensure_baseline_version: AB 测试 baseline 种子写入
- load_skill_content_for_batch: batch 快照读盘（prebuilt + workspace）
- invalidate_sidecar_backup: 移除 .bak 侧车文件

[POS]
技能优化版本双写层。统一 DB skill_versions 与磁盘 SKILL.md 的原子同步，供进化/AB/batch 共用。
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from myrm_agent_harness.agent.skills.discovery.sanitizer import SKILL_MD_FILE
from myrm_agent_harness.agent.skills.optimization.types import SkillQualityScore, SkillVersion

from app.adapters.skill_optimization.sqlalchemy_storage import SQLAlchemyStorage

logger = logging.getLogger(__name__)

_NEUTRAL_QUALITY = SkillQualityScore(
    success_rate=0.5,
    token_efficiency=0.5,
    execution_time=0.5,
    user_satisfaction=0.5,
    call_frequency=0.5,
)


def atomic_write_text_file(target: Path, content: str) -> None:
    """Atomically replace a text file (same pattern as evolution apply / config rollback)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=target.parent, prefix="skill_sync_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file_obj:
            file_obj.write(content)
        os.replace(tmp_path, target)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def invalidate_sidecar_backup(skill_path: Path) -> None:
    """Remove .bak sidecar after a successful version snapshot (single-track rollback)."""
    backup_path = skill_path.with_suffix(skill_path.suffix + ".bak")
    if backup_path.exists():
        backup_path.unlink()


async def load_skill_content_from_storage(skill_id: str) -> str | None:
    """Load current SKILL.md bytes for a registered prebuilt/local skill."""
    from app.core.skills.store.service import skills_service

    raw = await skills_service.get_skill_file(skill_id, SKILL_MD_FILE)
    if raw is None:
        return None
    return raw.decode("utf-8")


async def load_skill_content_for_batch(skill_id: str) -> str | None:
    """Load SKILL.md for batch snapshots: prebuilt storage first, then SkillStore path."""
    content = await load_skill_content_from_storage(skill_id)
    if content is not None:
        return content

    store = None
    try:
        from app.api.skills.evolution.helpers import _get_skill_store

        store = _get_skill_store()
        record = store.get_skill(skill_id)
        if record and record.path:
            skill_path = Path(record.path)
            if skill_path.is_file():
                return skill_path.read_text(encoding="utf-8")
            skill_md = skill_path / SKILL_MD_FILE if skill_path.is_dir() else skill_path
            if skill_md.exists():
                return skill_md.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to load workspace skill content for %s: %s", skill_id, exc)
    finally:
        if store is not None:
            store.close()
    return None


async def _resolve_quality_score(storage: SQLAlchemyStorage, skill_id: str) -> SkillQualityScore:
    latest = await storage.get_latest_quality(skill_id)
    return latest if latest is not None else _NEUTRAL_QUALITY


async def resolve_skill_md_path(skill_id: str) -> Path | None:
    """Resolve SKILL.md path via skills_service storage_path."""
    from app.core.skills.store.service import skills_service

    skill = await skills_service.get_skill(skill_id)
    if not skill or not skill.storage_path:
        return None
    return Path(skill.storage_path) / SKILL_MD_FILE


async def next_version_number(storage: SQLAlchemyStorage, skill_id: str) -> int:
    """Return the next monotonic version number for a skill."""
    versions = await storage.list_skill_versions(skill_id, limit=1)
    if not versions:
        return 1
    return versions[0].version + 1


async def sync_content_to_disk(
    skill_id: str,
    content: str,
    *,
    disk_path: Path | None = None,
) -> bool:
    """Write skill content to disk and bump skill config version."""
    path = disk_path if disk_path is not None else await resolve_skill_md_path(skill_id)
    if path is None:
        logger.warning("Cannot sync skill %s to disk: SKILL.md path not resolved", skill_id)
        return False

    atomic_write_text_file(path, content)

    from app.core.skills.config_version import bump_skill_config_version

    bump_skill_config_version()
    return True


async def persist_skill_version(
    storage: SQLAlchemyStorage,
    skill_id: str,
    content: str,
    *,
    created_by: str = "system",
    optimization_id: str | None = None,
    quality_score: SkillQualityScore | None = None,
    activate: bool = True,
    version: int | None = None,
    disk_path: Path | None = None,
    sync_disk: bool = True,
    invalidate_backup: bool = False,
) -> SkillVersion:
    """Save a skill snapshot to DB and optionally activate + sync disk."""
    ver = version if version is not None else await next_version_number(storage, skill_id)
    last_error: Exception | None = None
    saved: SkillVersion | None = None
    for attempt in range(2):
        try:
            saved = await storage.save_skill_version(
                skill_id=skill_id,
                version=ver,
                content=content,
                quality_score=quality_score,
                created_by=created_by,
                optimization_id=optimization_id,
            )
            break
        except Exception as exc:
            last_error = exc
            if attempt == 0:
                logger.warning("Retrying save_skill_version for %s v%s: %s", skill_id, ver, exc)
    if saved is None:
        raise last_error if last_error else RuntimeError(f"Failed to save skill version for {skill_id}")

    if activate:
        await storage.activate_version(skill_id, ver)
        if sync_disk:
            await sync_content_to_disk(skill_id, content, disk_path=disk_path)
            if invalidate_backup and disk_path is not None:
                invalidate_sidecar_backup(disk_path)
    return saved


async def activate_version_with_disk_sync(
    storage: SQLAlchemyStorage,
    skill_id: str,
    version: int,
) -> SkillVersion:
    """Activate a DB snapshot and mirror its content to disk."""
    skill_version = await storage.get_skill_version(skill_id, version)
    if skill_version is None:
        raise ValueError(f"Version {version} not found for skill {skill_id}")

    activated = await storage.activate_version(skill_id, version)
    disk_path = await resolve_skill_md_path(skill_id)
    await sync_content_to_disk(skill_id, skill_version.content, disk_path=disk_path)
    if disk_path is not None:
        invalidate_sidecar_backup(disk_path)
    return activated


async def restore_skill_snapshot(
    storage: SQLAlchemyStorage,
    skill_id: str,
    content: str,
    version: int,
) -> None:
    """Restore a skill to a prior snapshot (batch rollback / manual restore)."""
    existing = await storage.get_skill_version(skill_id, version)
    if existing is not None:
        await storage.activate_version(skill_id, version)
    else:
        await storage.save_skill_version(
            skill_id=skill_id,
            version=version,
            content=content,
            quality_score=_NEUTRAL_QUALITY,
            created_by="batch_rollback",
        )
        await storage.activate_version(skill_id, version)

    await sync_content_to_disk(skill_id, content)


async def ensure_baseline_version(
    storage: SQLAlchemyStorage,
    skill_id: str,
    baseline_version: int,
) -> tuple[SkillVersion, SkillQualityScore]:
    """Ensure baseline version exists in DB; seed from disk when missing."""
    existing = await storage.get_skill_version(skill_id, baseline_version)
    if existing is not None:
        score = existing.quality_score if existing.quality_score is not None else _NEUTRAL_QUALITY
        return existing, score

    content = await load_skill_content_for_batch(skill_id)
    if content is None:
        raise ValueError(f"Cannot seed baseline for {skill_id}: SKILL.md not found")

    quality_score = await _resolve_quality_score(storage, skill_id)
    saved = await persist_skill_version(
        storage,
        skill_id,
        content,
        version=baseline_version,
        created_by="ab_test_seed",
        quality_score=quality_score,
        activate=True,
    )
    return saved, quality_score
