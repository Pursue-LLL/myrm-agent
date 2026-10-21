"""Skill Change Contract — unified pre-replace snapshot + batch id recording.

[INPUT]
- manifest_snapshot::collect_manifest_snapshot_contents (POS: tree snapshot)
- state::set_last_replace_batch_id (POS: undo pointer)
- app.services.skill_optimization.bootstrap::get_skill_optimization_storage (POS: DB)

[OUTPUT]
- create_replace_snapshot: batch_id for rollback
- record_successful_replace: persist undo pointer after successful replace

[POS]
Server-layer SSOT for market/prebuilt/install-overwrite replace safety.
"""

from __future__ import annotations

import logging
import uuid

from myrm_agent_harness.api.skills import SkillInstallResult

from app.core.skills.models import Skill

logger = logging.getLogger(__name__)


class SkillReplaceBlockedError(Exception):
    """Replace refused (evolution locked, missing skill, snapshot failure)."""

    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


async def assert_replace_allowed(skill: Skill) -> None:
    if skill.evolution_locked:
        raise SkillReplaceBlockedError(
            "Skill is evolution-locked; remote replace is blocked.",
            error_code="evolution_locked",
        )


async def create_replace_snapshot(
    skill_id: str,
    skill_name: str,
    *,
    batch_kind: str,
) -> tuple[str, bool, frozenset[str]]:
    from app.core.skills.replace.manifest_snapshot import collect_manifest_snapshot_contents
    from app.services.skill_optimization.bootstrap import get_skill_optimization_storage
    from app.services.skill_optimization.rollback_service import RollbackService

    skill_md, resource_files, snapshot_truncated = await collect_manifest_snapshot_contents(skill_id)
    batch_id = f"{batch_kind}-{skill_id}-{uuid.uuid4().hex[:12]}"

    storage = get_skill_optimization_storage()
    async with storage._get_session() as session:
        service = RollbackService(session)
        metadata: dict[str, object] = {
            "batch_kind": "market_replace",
            "skill_name": skill_name,
            "existed_before_batch": True,
            "resource_files": resource_files,
            "snapshot_scope": "manifest_text",
            "snapshot_truncated": snapshot_truncated,
        }
        await service.insert_mutation_batch_snapshot(
            batch_id=batch_id,
            skill_id=skill_id,
            skill_content=skill_md,
            metadata=metadata,
        )
        await session.commit()
    logger.info("Created replace snapshot batch_id=%s skill_id=%s kind=%s", batch_id, skill_id, batch_kind)
    return batch_id, snapshot_truncated, frozenset(resource_files.keys())


async def record_successful_replace(skill_id: str, batch_id: str) -> None:
    from app.core.skills.replace.state import set_last_replace_batch_id

    await set_last_replace_batch_id(skill_id, batch_id)


def install_result_from_blocked(exc: SkillReplaceBlockedError, *, skill_name: str, skill_id: str) -> SkillInstallResult:
    return SkillInstallResult(
        success=False,
        skill_name=skill_name,
        skill_id=skill_id,
        error=str(exc),
        error_code=exc.error_code,
    )
