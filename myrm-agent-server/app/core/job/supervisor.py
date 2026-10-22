"""不可摧毁作业系统调度与巡检监督器。

负责周期性扫描过期切片、触发现场求证对账、并在切片边界原子摄入飞行中的用户输入。
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional

from app.core.job.models import (
    InFlightInputRecord,
    ReconciliationAction,
    RunStatus,
    SegmentRecord,
    SegmentStatus,
)
from app.core.job.reconciliation import CheckpointReconciler
from app.core.job.store import JobStore

logger = logging.getLogger(__name__)


class JobSupervisor:
    """作业监督巡检器。"""

    def __init__(
        self,
        store: JobStore,
        reconciler: Optional[CheckpointReconciler] = None,
    ) -> None:
        self._store = store
        self._reconciler = reconciler or CheckpointReconciler(store)

    async def tick(self, now_mono: Optional[float] = None) -> int:
        """执行单次巡检脉冲。

        返回处理并对账自愈的切片数量。
        """
        now = now_mono if now_mono is not None else time.monotonic()
        expired_segments: List[SegmentRecord] = await self._store.find_expired_segments(now)
        reconciled_count = 0

        for seg in expired_segments:
            action: ReconciliationAction = (
                await self._reconciler.reconcile_expired_segment(seg)
            )
            logger.info(
                "Supervised segment %s expired; applied action: %s",
                seg.segment_id,
                action.value,
            )
            reconciled_count += 1

        return reconciled_count

    async def ingest_inputs_at_boundary(
        self,
        run_id: str,
        target_segment_id: str,
    ) -> List[InFlightInputRecord]:
        """切片边界原子摄入排队中的用户飞入输入。"""
        return await self._store.claim_pending_inputs_for_segment(
            run_id=run_id,
            segment_id=target_segment_id,
        )

    async def complete_segment_and_advance(
        self,
        segment_id: str,
        fencing_token: int,
        is_last_segment: bool = False,
        final_output: Optional[str] = None,
    ) -> bool:
        """切片成功结算，标记关联飞入输入已消费，并推动 Run 状态流转。"""
        settled = await self._store.settle_segment(
            segment_id=segment_id,
            fencing_token=fencing_token,
            status=SegmentStatus.COMPLETED,
        )
        if not settled:
            return False

        # 原子标记摄入的输入为已消费
        await self._store.mark_inputs_consumed(segment_id)

        # 获取切片以更新 Run
        seg = await self._store.get_segment(segment_id)
        if seg is not None and is_last_segment:
            await self._store.update_run_status(
                run_id=seg.run_id,
                status=RunStatus.COMPLETED,
                final_output=final_output,
            )

        return True
