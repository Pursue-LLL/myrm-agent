"""Server hook: persist skill_manage batch snapshots for later rollback."""

from __future__ import annotations

import logging

from myrm_agent_harness.agent.meta_tools.skills.manage.batch_runner import SkillBatchSnapshot

logger = logging.getLogger(__name__)


class ServerSkillManageBatchHook:
    """Persist pre-mutation snapshots into batch_snapshots (batch_kind=skill_mutation)."""

    async def on_batch_committed(
        self,
        batch_id: str,
        snapshots: dict[str, SkillBatchSnapshot],
    ) -> None:
        from app.services.skill_optimization.bootstrap import get_skill_optimization_storage
        from app.services.skill_optimization.rollback_service import RollbackService
        from app.services.skills.write_orchestrator import resolve_skill_id_by_name

        storage = get_skill_optimization_storage()
        async with storage._get_session() as session:
            service = RollbackService(session)
            try:
                for snap in snapshots.values():
                    skill_id = await resolve_skill_id_by_name(snap.skill_name)
                    if not skill_id:
                        raise RuntimeError(
                            f"Cannot persist batch snapshot: unresolved skill name {snap.skill_name!r}."
                        )
                    metadata: dict[str, object] = {
                        "batch_kind": "skill_mutation",
                        "resource_files": snap.resources,
                        "existed_before_batch": snap.existed_before_batch,
                    }
                    await service.insert_mutation_batch_snapshot(
                        batch_id=batch_id,
                        skill_id=skill_id,
                        skill_content=snap.skill_md or "",
                        metadata=metadata,
                        commit=False,
                    )
                await session.commit()
            except Exception:
                await session.rollback()
                raise
