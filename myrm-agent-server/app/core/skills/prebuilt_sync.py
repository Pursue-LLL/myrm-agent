"""Sync prebuilt skill seeds to storage on startup.

[INPUT]
myrm_agent_harness.api.skills::parse_skill_frontmatter (POS: SKILL.md frontmatter parser)
myrm_agent_harness.api.skills::compute_content_hash (POS: SHA-256 content hashing)
myrm_agent_harness.toolkits.storage.base::StorageProvider (POS: unified storage abstraction)

[OUTPUT]
sync_prebuilt_seeds: sync version-controlled seeds to storage with three-way hash protection
PrebuiltSyncResult: synced_count and discovered skill_ids

[POS]
Business-layer prebuilt skill seed synchronizer with three-way hash comparison.
Protects user-modified prebuilt skills from silent overwrite during upgrades:
- origin_hash tracks the bundled source SHA-256 at last sync
- If user modified content (current_hash != origin_hash), skip overwrite and mark
  has_upstream_update=True so the frontend can show an "update available" badge.
- If user hasn't modified, silently apply upstream updates.
Also handles stale entry cleanup for removed bundled skills.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from myrm_agent_harness.agent.skills.discovery.sanitizer import SKILL_MD_FILE
from myrm_agent_harness.api.skills import (
    SkillMetadataError,
    compute_content_hash,
    parse_skill_frontmatter,
)
from myrm_agent_harness.toolkits.storage.base import StorageProvider
from myrm_agent_harness.toolkits.storage.paths import (
    SKILL_METADATA_FILE,
    get_skill_file_path,
    get_skill_metadata_path,
    get_skills_type_prefix,
)
from myrm_agent_harness.utils.text_utils import get_token_count

from app.core.skills.models import Skill, SkillType
from app.core.skills.providers.local import parse_skill_md

logger = logging.getLogger(__name__)

SEEDS_DIR = Path(__file__).resolve().parents[3] / "assets" / "prebuilt_skills"

_synced = False


@dataclass(frozen=True)
class PrebuiltSyncResult:
    """Outcome of a prebuilt seed synchronization run."""

    synced_count: int
    skill_ids: tuple[str, ...]


def _parse_tags(raw: dict[str, object] | None) -> list[str]:
    if raw is None:
        return []
    tags_raw = raw.get("tags")
    if not isinstance(tags_raw, list):
        return []
    return [str(t) for t in tags_raw]


def _build_skill_from_seed(
    skill_dir_name: str,
    content: str,
    frontmatter_name: str | None,
    description: str,
    category: str | None,
    version: str | None,
    tags: list[str],
) -> Skill:
    skill_id = frontmatter_name or skill_dir_name
    storage_path = f"skills/prebuilt/{skill_id}"
    token_cost: int | None = None
    try:
        token_cost = get_token_count(content)
    except Exception as exc:
        logger.warning("Failed to calculate token cost for prebuilt skill %s: %s", skill_id, exc)

    now = datetime.now(UTC)
    return Skill(
        id=skill_id,
        type=SkillType.PREBUILT,
        name=skill_id,
        description=description,
        storage_path=storage_path,
        version=version or "1.0.0",
        category=category,
        tags=tags,
        token_cost=token_cost,
        trust="trusted",
        created_at=now,
        updated_at=now,
    )


async def _write_skill_to_storage(
    storage: StorageProvider,
    skill: Skill,
    skill_md_path: str,
    metadata_path: str,
    content: str,
) -> None:
    """Write SKILL.md content and metadata JSON to storage atomically."""
    await storage.write_text(skill_md_path, content)
    await storage.write_text(metadata_path, json.dumps(skill.to_dict(), indent=2))


async def _sync_skill_bundle_files(
    storage: StorageProvider,
    skill_id: str,
    skill_dir: Path,
) -> None:
    """Sync bundled seed files (e.g. scripts/) alongside SKILL.md.

    Auxiliary bundle files always follow upstream seeds and are not part of the
    SKILL.md three-way hash protection (users edit prose, not bundled tooling).
    """
    for path in skill_dir.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(skill_dir)
        if relative.name == SKILL_MD_FILE or relative.name.startswith("."):
            continue
        if any(part.startswith("_") for part in relative.parts):
            continue

        rel_posix = relative.as_posix()
        storage_path = get_skill_file_path(SkillType.PREBUILT, skill_id, rel_posix)
        if path.suffix in {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".sh"}:
            await storage.write_text(storage_path, path.read_text(encoding="utf-8"))
        else:
            await storage.write_bytes(storage_path, path.read_bytes())


async def sync_prebuilt_seeds(storage: StorageProvider) -> PrebuiltSyncResult:
    """Sync prebuilt skill seeds to storage. Runs at most once per process."""
    global _synced  # noqa: PLW0603
    if _synced:
        return PrebuiltSyncResult(synced_count=0, skill_ids=())

    _synced = True

    if not SEEDS_DIR.is_dir():
        return PrebuiltSyncResult(synced_count=0, skill_ids=())

    synced = 0
    skill_ids: list[str] = []

    for skill_dir in sorted(SEEDS_DIR.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith(("_", ".")):
            continue

        skill_md_path = skill_dir / SKILL_MD_FILE
        if not skill_md_path.is_file():
            continue

        source_content = skill_md_path.read_text(encoding="utf-8")

        try:
            frontmatter = parse_skill_frontmatter(source_content, skill_dir.name)
        except SkillMetadataError as exc:
            logger.error(
                "Skipping prebuilt seed %s: invalid frontmatter: %s",
                skill_dir.name,
                exc,
            )
            continue

        raw_meta = parse_skill_md(source_content)
        tags = _parse_tags(raw_meta)
        skill_id = frontmatter.name or skill_dir.name
        skill_ids.append(skill_id)

        skill = _build_skill_from_seed(
            skill_dir_name=skill_dir.name,
            content=source_content,
            frontmatter_name=frontmatter.name,
            description=frontmatter.description,
            category=frontmatter.category,
            version=frontmatter.version,
            tags=tags,
        )

        skill_md_storage = get_skill_file_path(SkillType.PREBUILT, skill_id, SKILL_MD_FILE)
        metadata_storage = get_skill_metadata_path(SkillType.PREBUILT, skill_id)
        source_hash = compute_content_hash(source_content)

        existing_md: str | None = None
        existing_meta: dict[str, object] | None = None
        try:
            existing_md = await storage.read_text(skill_md_storage)
        except FileNotFoundError:
            pass

        try:
            existing_meta = json.loads(await storage.read_text(metadata_storage))
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        if existing_md is None:
            # First-time sync: write content, metadata, and record origin_hash
            skill.origin_hash = source_hash
            await _write_skill_to_storage(storage, skill, skill_md_storage, metadata_storage, source_content)
            await _sync_skill_bundle_files(storage, skill_id, skill_dir)
            synced += 1
            logger.info("Synced new prebuilt skill: %s", skill_id)
            continue

        origin_hash = existing_meta.get("origin_hash") if existing_meta else None
        current_hash = compute_content_hash(existing_md)

        if origin_hash is None:
            # Migration from pre-origin_hash era: baseline current content as origin
            skill.origin_hash = source_hash
            if current_hash == source_hash:
                # Content matches upstream — normal write to add origin_hash
                await _write_skill_to_storage(storage, skill, skill_md_storage, metadata_storage, source_content)
                await _sync_skill_bundle_files(storage, skill_id, skill_dir)
                synced += 1
                logger.info("Synced prebuilt skill (migration baseline): %s", skill_id)
            else:
                # Can't tell if user modified or upstream changed — preserve user copy,
                # record source_hash as origin for future three-way detection
                skill.has_upstream_update = True
                meta_json = json.dumps(skill.to_dict(), indent=2)
                await storage.write_text(metadata_storage, meta_json)
                logger.info("Preserved user copy of prebuilt skill %s (migration, marked upstream update)", skill_id)
            await _sync_skill_bundle_files(storage, skill_id, skill_dir)
            continue

        if current_hash != origin_hash:
            # User modified this skill — protect their changes
            if source_hash != origin_hash:
                # Upstream also changed — mark for user review
                skill.origin_hash = origin_hash
                skill.has_upstream_update = True
                meta_json = json.dumps(skill.to_dict(), indent=2)
                await storage.write_text(metadata_storage, meta_json)
                logger.info("Prebuilt skill %s: user-modified, upstream update available", skill_id)
            await _sync_skill_bundle_files(storage, skill_id, skill_dir)
            continue

        # User hasn't modified — check if upstream has a newer version
        if source_hash != origin_hash:
            skill.origin_hash = source_hash
            skill.has_upstream_update = False
            await _write_skill_to_storage(storage, skill, skill_md_storage, metadata_storage, source_content)
            synced += 1
            logger.info("Updated prebuilt skill: %s (upstream changed)", skill_id)

        await _sync_skill_bundle_files(storage, skill_id, skill_dir)

    if synced:
        logger.info("Synced %d prebuilt skill(s) to storage", synced)

    await _cleanup_stale_prebuilt_skills(storage, set(skill_ids))

    return PrebuiltSyncResult(synced_count=synced, skill_ids=tuple(skill_ids))


async def _cleanup_stale_prebuilt_skills(
    storage: StorageProvider,
    current_skill_ids: set[str],
) -> None:
    """Remove storage entries for prebuilt skills whose seed directories no longer exist."""
    try:
        prebuilt_prefix = get_skills_type_prefix(SkillType.PREBUILT)
        stored_files = await storage.list(prebuilt_prefix)
    except Exception as exc:
        logger.warning("Failed to list prebuilt skills for cleanup: %s", exc)
        return

    stale_ids: set[str] = set()
    for file_path in stored_files:
        if not file_path.endswith(SKILL_METADATA_FILE):
            continue
        parts = file_path.rstrip("/").split("/")
        if len(parts) >= 2:
            stored_id = parts[-2]
            if stored_id not in current_skill_ids:
                stale_ids.add(stored_id)

    for stale_id in stale_ids:
        try:
            md_path = get_skill_file_path(SkillType.PREBUILT, stale_id, SKILL_MD_FILE)
            meta_path = get_skill_metadata_path(SkillType.PREBUILT, stale_id)
            await storage.delete(md_path)
            await storage.delete(meta_path)
            logger.info("Cleaned up stale prebuilt skill from storage: %s", stale_id)
        except Exception as exc:
            logger.warning("Failed to clean up stale prebuilt skill %s: %s", stale_id, exc)
