"""Sync prebuilt skill seeds to storage on startup.

[INPUT]
myrm_agent_harness.api.skills::parse_skill_frontmatter (POS: SKILL.md frontmatter parser)
myrm_agent_harness.api.skills::compute_content_hash (POS: SHA-256 content hashing)
myrm_agent_harness.backends.skills.types::SkillRequires (POS: framework runtime requirement declaration)
myrm_agent_harness.toolkits.storage.base::StorageProvider (POS: unified storage abstraction)

[OUTPUT]
sync_prebuilt_seeds: sync version-controlled seeds to storage with three-way hash protection
verify_reused_sync: the full reconciliation a start that reused the last sync left for later
PrebuiltSyncResult: synced_count and discovered skill_ids

[POS]
Business-layer prebuilt skill seed synchronizer with three-way hash comparison.
Protects user-modified prebuilt skills from silent overwrite during upgrades:
- origin_hash tracks the bundled source SHA-256 at last sync
- If user modified content (current_hash != origin_hash), skip overwrite and mark
  has_upstream_update=True so the frontend can show an "update available" badge.
- If user hasn't modified, silently apply upstream updates.
After each sync the snapshot's ``requires`` matches the SKILL.md that stays in storage (the user's copy
when it differs from the seed), so the Skills page gates what the runtime gates. Editing SKILL.md
through the files API refreshes it at the next sync. The snapshot also carries the seed's declared
``required_permissions``, which the enable-time permission gate reads.
A seed's snapshot (token count, tags) is built only when the seed is installed or changed; seeds that
already match their stored copy are never tokenized, so a later start spends no pre-listen time counting tokens.
A start may ask to reuse the last complete sync (``reuse_unchanged``, see ``prebuilt_sync_state``): its reconciliation
then runs after the first screen, in ``verify_reused_sync``; every other start reconciles in full before it returns.
Also handles stale entry cleanup for removed bundled skills.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from myrm_agent_harness.agent.skills.market.sanitizer import SKILL_MD_FILE
from myrm_agent_harness.api.skills import (
    SkillMetadataError,
    compute_content_hash,
    parse_skill_frontmatter,
)
from myrm_agent_harness.backends.skills.types import SkillRequires
from myrm_agent_harness.toolkits.storage.base import StorageProvider
from myrm_agent_harness.utils.text_utils import get_token_count

from app.core.skills.models import Skill, SkillType
from app.core.skills.prebuilt_bundle_sync import sync_skill_bundle_files
from app.core.skills.prebuilt_sync_state import (
    iter_seed_dirs,
    load_reusable_skill_ids,
    save_sync_state,
    seeds_fingerprint,
)
from app.core.skills.providers.local import parse_skill_md
from app.core.storage.paths import (
    SKILL_METADATA_FILE,
    get_skill_file_path,
    get_skill_metadata_path,
    get_skills_type_prefix,
)

logger = logging.getLogger(__name__)

SEEDS_DIR = Path(__file__).resolve().parents[3] / "assets" / "prebuilt_skills"

_synced = False


@dataclass(frozen=True)
class PrebuiltSyncResult:
    """Outcome of a prebuilt seed synchronization run."""

    synced_count: int
    skill_ids: tuple[str, ...]


# Fingerprint of the last complete sync this start reused, until ``verify_reused_sync`` has reconciled it.
_reused_fingerprint: str | None = None


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
    allowed_tools: list[str] | None = None,
    requires: SkillRequires | None = None,
    required_oauth_issuers: list[str] | None = None,
    required_mcp_server_ids: list[str] | None = None,
    required_permissions: list[str] | None = None,
) -> Skill:
    """Build the storage snapshot of a bundled seed; counting its tokens is the expensive part."""
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
        tags=_parse_tags(parse_skill_md(content)),
        token_cost=token_cost,
        allowed_tools=allowed_tools,
        requires=requires or SkillRequires(),
        required_oauth_issuers=required_oauth_issuers or [],
        required_mcp_server_ids=required_mcp_server_ids or [],
        required_permissions=required_permissions or [],
        trust="trusted",
        created_at=now,
        updated_at=now,
    )


def _kept_requires(
    stored_md: str,
    matches_seed: bool,
    seed_requires: SkillRequires,
    skill_dir_name: str,
    snapshot: dict[str, object] | None,
) -> SkillRequires:
    """``requires`` of the SKILL.md that stays in storage unless the seed replaces it.

    The runtime parses the stored copy, so a user-edited copy decides, not the seed. An unparsable
    copy keeps the snapshot's current value rather than guessing.
    """
    if matches_seed:
        return seed_requires
    try:
        return parse_skill_frontmatter(stored_md, skill_dir_name).requires or SkillRequires()
    except SkillMetadataError:
        persisted = snapshot.get("requires") if snapshot else None
        return SkillRequires.from_dict(persisted if isinstance(persisted, dict) else None)


async def _patch_snapshot_requires(
    storage: StorageProvider,
    metadata_path: str,
    snapshot: dict[str, object] | None,
    requires: SkillRequires,
) -> None:
    """Align the ``requires`` of a snapshot the sync is not rewriting with the SKILL.md kept in storage.

    The Skills page gates on the snapshot while the runtime gates on the stored SKILL.md, so both
    must declare the same requirements.
    """
    if snapshot is None or snapshot.get("requires") == requires.to_dict():
        return
    await storage.write_text(metadata_path, json.dumps({**snapshot, "requires": requires.to_dict()}, indent=2))
    logger.info("Refreshed requires in prebuilt skill snapshot: %s", metadata_path)


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


async def sync_prebuilt_seeds(storage: StorageProvider, *, reuse_unchanged: bool = False) -> PrebuiltSyncResult:
    """Sync prebuilt skill seeds to storage. Runs at most once per process.

    With ``reuse_unchanged`` (the boot, in local mode) a start whose seeds are those of the last complete sync, and whose
    stored copies are all present, returns that sync's skill ids at once: the reconciliation would change nothing the
    first screen reads, and ``verify_reused_sync`` runs it later. Any other start reconciles in full before it returns
    and then records the seeds it completed for.
    """
    global _synced, _reused_fingerprint  # noqa: PLW0603
    if _synced:
        return PrebuiltSyncResult(synced_count=0, skill_ids=())

    _synced = True

    if not SEEDS_DIR.is_dir():
        return PrebuiltSyncResult(synced_count=0, skill_ids=())

    fingerprint = await asyncio.to_thread(seeds_fingerprint, SEEDS_DIR) if reuse_unchanged else None
    if fingerprint is not None:
        reusable_ids = await load_reusable_skill_ids(storage, fingerprint)
        if reusable_ids is not None:
            _reused_fingerprint = fingerprint
            logger.info("Prebuilt skills unchanged since the last complete sync (%d skills)", len(reusable_ids))
            return PrebuiltSyncResult(synced_count=0, skill_ids=reusable_ids)

    result = await _reconcile(storage)
    if fingerprint is not None:
        await save_sync_state(storage, fingerprint, result.skill_ids)
    return result


async def verify_reused_sync(storage: StorageProvider) -> PrebuiltSyncResult | None:
    """Reconcile in full a start that reused the last complete sync; None when there is nothing to reconcile.

    It repairs what changed in storage since that sync (a bundle file removed, a SKILL.md edited through the files API,
    a stale entry left behind) exactly as a start that reconciled before listening would have.
    """
    global _reused_fingerprint  # noqa: PLW0603
    fingerprint, _reused_fingerprint = _reused_fingerprint, None
    if fingerprint is None:
        return None
    result = await _reconcile(storage)
    await save_sync_state(storage, fingerprint, result.skill_ids)
    return result


async def _reconcile(storage: StorageProvider) -> PrebuiltSyncResult:
    """Bring storage in line with every seed: install, update, protect user copies, repair, drop stale entries."""
    synced = 0
    skill_ids: list[str] = []

    for skill_dir in iter_seed_dirs(SEEDS_DIR):
        source_content = (skill_dir / SKILL_MD_FILE).read_text(encoding="utf-8")

        try:
            frontmatter = parse_skill_frontmatter(source_content, skill_dir.name)
        except SkillMetadataError as exc:
            logger.error(
                "Skipping prebuilt seed %s: invalid frontmatter: %s",
                skill_dir.name,
                exc,
            )
            continue

        skill_id = frontmatter.name or skill_dir.name
        skill_ids.append(skill_id)

        allowed_tools_list = (
            [t.strip() for t in frontmatter.allowed_tools.split() if t.strip()] if frontmatter.allowed_tools else None
        )
        seed_requires = frontmatter.requires or SkillRequires()
        # Only installs and upstream changes write a snapshot; unchanged seeds (every start after the
        # first) skip building it, which would tokenize the whole SKILL.md of every bundled skill.
        build_skill = partial(
            _build_skill_from_seed,
            skill_dir_name=skill_dir.name,
            content=source_content,
            frontmatter_name=frontmatter.name,
            description=frontmatter.description,
            category=frontmatter.category,
            version=frontmatter.version,
            allowed_tools=allowed_tools_list,
            requires=seed_requires,
            required_oauth_issuers=frontmatter.required_oauth_issuers,
            required_mcp_server_ids=frontmatter.required_mcp_server_ids,
            required_permissions=[permission.value for permission in frontmatter.required_permissions],
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
            skill = build_skill()
            skill.origin_hash = source_hash
            await _write_skill_to_storage(storage, skill, skill_md_storage, metadata_storage, source_content)
            await sync_skill_bundle_files(storage, skill_id, skill_dir)
            synced += 1
            logger.info("Synced new prebuilt skill: %s", skill_id)
            continue

        persisted_origin = existing_meta.get("origin_hash") if existing_meta else None
        origin_hash = persisted_origin if isinstance(persisted_origin, str) else None
        current_hash = compute_content_hash(existing_md)
        kept_requires = _kept_requires(existing_md, current_hash == source_hash, seed_requires, skill_dir.name, existing_meta)

        if origin_hash is None:
            # Migration from pre-origin_hash era: baseline current content as origin
            skill = build_skill()
            skill.origin_hash = source_hash
            if current_hash == source_hash:
                # Content matches upstream — normal write to add origin_hash
                await _write_skill_to_storage(storage, skill, skill_md_storage, metadata_storage, source_content)
                await sync_skill_bundle_files(storage, skill_id, skill_dir)
                synced += 1
                logger.info("Synced prebuilt skill (migration baseline): %s", skill_id)
            else:
                # Can't tell if user modified or upstream changed — preserve user copy,
                # record source_hash as origin for future three-way detection
                skill.has_upstream_update = True
                skill.requires = kept_requires
                meta_json = json.dumps(skill.to_dict(), indent=2)
                await storage.write_text(metadata_storage, meta_json)
                logger.info("Preserved user copy of prebuilt skill %s (migration, marked upstream update)", skill_id)
            await sync_skill_bundle_files(storage, skill_id, skill_dir)
            continue

        if current_hash != origin_hash:
            # User modified this skill — protect their changes
            if source_hash != origin_hash:
                # Upstream also changed — mark for user review
                skill = build_skill()
                skill.origin_hash = origin_hash
                skill.has_upstream_update = True
                skill.requires = kept_requires
                meta_json = json.dumps(skill.to_dict(), indent=2)
                await storage.write_text(metadata_storage, meta_json)
                logger.info("Prebuilt skill %s: user-modified, upstream update available", skill_id)
            else:
                await _patch_snapshot_requires(storage, metadata_storage, existing_meta, kept_requires)
            await sync_skill_bundle_files(storage, skill_id, skill_dir)
            continue

        # User hasn't modified — check if upstream has a newer version
        if source_hash != origin_hash:
            skill = build_skill()
            skill.origin_hash = source_hash
            skill.has_upstream_update = False
            await _write_skill_to_storage(storage, skill, skill_md_storage, metadata_storage, source_content)
            synced += 1
            logger.info("Updated prebuilt skill: %s (upstream changed)", skill_id)
        else:
            await _patch_snapshot_requires(storage, metadata_storage, existing_meta, kept_requires)

        await sync_skill_bundle_files(storage, skill_id, skill_dir)

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
