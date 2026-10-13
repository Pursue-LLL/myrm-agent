"""
[INPUT]
- myrm_agent_harness.agent.meta_tools.skills.manage.batch_runner (POS: skill_manage 批次快照类型 SkillBatchSnapshot)
- app.services.skill_optimization.bootstrap (POS: 存储会话获取)
- app.services.skill_optimization.rollback_service (POS: batch_snapshots 写入)
- app.services.skills.write_orchestrator (POS: skill 名称解析为 skill_id)
[OUTPUT]
- ServerSkillManageBatchHook (harness 批次钩子的服务端实现：单事务写入 batch_kind=skill_mutation 快照)
[POS]
skill_manage 批次提交后的快照落库钩子：任一 skill 无法解析则整批回滚并抛错（fail-closed）。
"""

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
                        raise RuntimeError(f"Cannot persist batch snapshot: unresolved skill name {snap.skill_name!r}.")
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
