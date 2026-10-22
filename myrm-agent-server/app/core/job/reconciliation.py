"""现场求证对账自愈器。

实现四级现场求证与对账决策：
1. RETRY_SAFE: 纯读/无副作用，安全重派为 PENDING；
2. RESUME_FROM_EVIDENCE: 已有持久化中间检查点，恢复执行；
3. RECONCILE_MESSAGE: 已向外部成功发送且有消息凭证，补齐 SUCCESS 对账；
4. BLOCK_UNCERTAIN_SIDE_EFFECT: 无法求证的黑盒写操作，转为 PAUSED_FOR_APPROVAL 等待人工裁决。
"""

from __future__ import annotations

import logging
from typing import Optional

from app.core.job.models import (
    CheckpointEvidence,
    ReconciliationAction,
    RunStatus,
    SegmentRecord,
    SegmentStatus,
)
from app.core.job.store import JobStore

logger = logging.getLogger(__name__)


class CheckpointReconciler:
    """四级现场求证对账核心引擎。"""

    def __init__(self, store: JobStore) -> None:
        self._store = store

    async def reconcile_expired_segment(
        self,
        segment: SegmentRecord,
    ) -> ReconciliationAction:
        """对租约已超期的切片执行现场证据链求证与自愈处置。"""
        evidence: Optional[CheckpointEvidence] = segment.checkpoint_evidence

        # 级别 1: 无副作用/纯读/无证据 -> 安全重派
        if evidence is None or not evidence.has_side_effect:
            logger.info(
                "Reconcile segment %s as RETRY_SAFE (no side effect)",
                segment.segment_id,
            )
            await self._store.reset_segment_to_pending(
                segment_id=segment.segment_id,
                expected_fencing_token=segment.fencing_token,
            )
            return ReconciliationAction.RETRY_SAFE

        # 级别 3: 外部消息已具明确凭证 -> 补齐成功对账
        if evidence.external_message_id is not None:
            logger.info(
                "Reconcile segment %s as RECONCILE_MESSAGE (msg_id=%s)",
                segment.segment_id,
                evidence.external_message_id,
            )
            await self._store.settle_segment(
                segment_id=segment.segment_id,
                fencing_token=segment.fencing_token,
                status=SegmentStatus.COMPLETED,
            )
            return ReconciliationAction.RECONCILE_MESSAGE

        # 级别 2: 具有持久化中间状态快照 -> 从证据检查点断点续传
        if evidence.persisted_state_digest is not None:
            logger.info(
                "Reconcile segment %s as RESUME_FROM_EVIDENCE (digest=%s)",
                segment.segment_id,
                evidence.persisted_state_digest,
            )
            await self._store.reset_segment_to_pending(
                segment_id=segment.segment_id,
                expected_fencing_token=segment.fencing_token,
            )
            return ReconciliationAction.RESUME_FROM_EVIDENCE

        # 级别 4: 不确定副作用写操作 -> 阻断并转人工审批
        logger.warning(
            "Reconcile segment %s as BLOCK_UNCERTAIN_SIDE_EFFECT (tool=%s)",
            segment.segment_id,
            evidence.last_tool_name,
        )
        await self._store.settle_segment(
            segment_id=segment.segment_id,
            fencing_token=segment.fencing_token,
            status=SegmentStatus.FAILED,
            error_message=f"Uncertain side effect in tool {evidence.last_tool_name}",
        )
        await self._store.update_run_status(
            run_id=segment.run_id,
            status=RunStatus.PAUSED_FOR_APPROVAL,
            error_message="Execution paused: uncertain side effect requires approval",
        )
        return ReconciliationAction.BLOCK_UNCERTAIN_SIDE_EFFECT
