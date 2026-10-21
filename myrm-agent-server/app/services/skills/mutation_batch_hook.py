"""
[INPUT]
- myrm_agent_harness.agent.meta_tools.skills.manage.batch_runner (POS: skill_manage 批次快照类型 SkillBatchSnapshot)
- app.services.skill_optimization.bootstrap (POS: 存储会话获取)
- app.services.skill_optimization.rollback_service (POS: batch_snapshots 写入)
- app.services.skills.write_orchestrator (POS: skill 名称解析为 skill_id)
- app.services.skills.mutation_batch_stream (POS: 批次提交事件契约，供 Task Steps 关联撤销入口)
- myrm_agent_harness.utils.runtime.progress_sink (POS: 工具向 Agent SSE 流推送事件的通道)
[OUTPUT]
- ServerSkillManageBatchHook (harness 批次钩子的服务端实现：单事务写入 batch_kind=skill_mutation 快照，提交后向流广播批次 id)
[POS]
skill_manage 批次提交后的快照落库钩子：任一 skill 无法解析则整批回滚并抛错（fail-closed）；
快照落库后才广播批次 id，广播失败不影响已提交的批次。
"""

from __future__ import annotations

import logging

from myrm_agent_harness.agent.meta_tools.skills.manage.batch_runner import SkillBatchSnapshot
from myrm_agent_harness.utils.runtime.progress_sink import get_tool_progress_sink

from app.services.skills.mutation_batch_stream import build_batch_committed_event

logger = logging.getLogger(__name__)


async def _announce_committed_batch(batch_id: str) -> None:
    """Tell the chat stream which batch the running skill_manage call committed, so Task Steps can offer Undo."""
    sink = get_tool_progress_sink()
    if sink is None:
        return
    try:
        await sink.emit(build_batch_committed_event(batch_id))
    except Exception:
        logger.warning("Failed to announce committed skill batch %s to the stream.", batch_id, exc_info=True)


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
        await _announce_committed_batch(batch_id)
