"""Post-replace honesty check for bounded manifest snapshots.

[INPUT]
- manifest_snapshot::_is_snapshot_candidate (POS: snapshot file policy)
- app.core.skills.store.service::skills_service (POS: post-install file list)

[OUTPUT]
- assess_post_replace_snapshot_honesty: True when rollback cannot cover the full tree

[POS]
Skill Change Contract honesty signal after market replace (non-text or uncaptured files).
"""

from __future__ import annotations

from myrm_agent_harness.agent.skills.market.sanitizer import SKILL_MD_FILE
from myrm_agent_harness.toolkits.storage.paths import SKILL_METADATA_FILE

from app.core.skills.replace.manifest_snapshot import _is_snapshot_candidate

_SKIP_PATHS = frozenset({SKILL_METADATA_FILE, "origin.json", ".stats.json", ".replace_state.json"})


async def assess_post_replace_snapshot_honesty(
    skill_id: str,
    *,
    pre_collect_truncated: bool,
    snapshotted_resource_paths: frozenset[str],
) -> bool:
    """Return True when undo snapshot does not cover the installed skill tree."""
    if pre_collect_truncated:
        return True

    from app.core.skills.store.service import skills_service

    files = await skills_service.list_skill_files(skill_id)
    covered = set(snapshotted_resource_paths) | {SKILL_MD_FILE}

    for rel in files:
        name = rel.rsplit("/", 1)[-1]
        if name.startswith("."):
            continue
        if rel in _SKIP_PATHS:
            continue
        if not _is_snapshot_candidate(rel):
            return True
        if rel not in covered:
            return True
    return False


async def merge_snapshot_honesty_after_install(
    target_id: str,
    *,
    snapshot_truncated: bool,
    snapshotted_paths: frozenset[str],
    batch_id: str | None,
    install_success: bool,
) -> bool:
    if not install_success or not batch_id or not target_id:
        return snapshot_truncated
    post = await assess_post_replace_snapshot_honesty(
        target_id,
        pre_collect_truncated=snapshot_truncated,
        snapshotted_resource_paths=snapshotted_paths,
    )
    return snapshot_truncated or post


async def persist_replace_snapshot_truncated_flag(
    batch_id: str,
    skill_id: str,
    *,
    snapshot_truncated: bool,
) -> None:
    """Write post-replace honesty into batch snapshot metadata for later UI/rollback."""
    if not snapshot_truncated:
        return
    from sqlalchemy import select

    from app.database.models import BatchSnapshot
    from app.services.skill_optimization.bootstrap import get_skill_optimization_storage

    storage = get_skill_optimization_storage()
    async with storage._get_session() as session:
        result = await session.execute(
            select(BatchSnapshot).where(
                BatchSnapshot.batch_id == batch_id,
                BatchSnapshot.skill_id == skill_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return
        metadata = dict(row.skill_metadata or {})
        if metadata.get("snapshot_truncated") is True:
            return
        metadata["snapshot_truncated"] = True
        row.skill_metadata = metadata
        await session.commit()
