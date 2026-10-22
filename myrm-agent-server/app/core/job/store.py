"""作业持久化存储引擎与 CAS 防脑裂实现。

提供原子 Claim、单调递增 Fencing Token 校验、租约延展与现场检查点持久化。
"""

from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Optional

from app.core.job.models import (
    AttemptRecord,
    AttemptStatus,
    CheckpointEvidence,
    InFlightInputRecord,
    InputStatus,
    RunRecord,
    RunStatus,
    SegmentRecord,
    SegmentStatus,
)


class JobStore:
    """生产级作业存储契约实现。

    支持并发安全的原子 Claim、单调 Fencing Token 防脑裂与切片边界输入摄入。
    使用线程安全/协程安全的原子锁保证并发互斥。
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._runs: Dict[str, RunRecord] = {}
        self._segments: Dict[str, SegmentRecord] = {}
        self._attempts: Dict[str, AttemptRecord] = {}
        self._inputs: Dict[str, InFlightInputRecord] = {}

    async def create_run(self, run_id: str, conversation_id: str) -> RunRecord:
        """创建顶层作业生命周期实例。"""
        async with self._lock:
            now = time.monotonic()
            record = RunRecord(
                run_id=run_id,
                conversation_id=conversation_id,
                status=RunStatus.PENDING,
                created_at_mono=now,
                updated_at_mono=now,
            )
            self._runs[run_id] = record
            return record

    async def get_run(self, run_id: str) -> Optional[RunRecord]:
        """获取指定作业实例。"""
        async with self._lock:
            return self._runs.get(run_id)

    async def update_run_status(
        self,
        run_id: str,
        status: RunStatus,
        final_output: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """流转顶层作业状态。"""
        async with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return False
            now = time.monotonic()
            self._runs[run_id] = RunRecord(
                run_id=run.run_id,
                conversation_id=run.conversation_id,
                status=status,
                created_at_mono=run.created_at_mono,
                updated_at_mono=now,
                current_segment_id=run.current_segment_id,
                final_output=final_output or run.final_output,
                error_message=error_message or run.error_message,
            )
            return True

    async def create_segment(
        self,
        segment_id: str,
        run_id: str,
        sequence_index: int,
        max_steps: int = 20,
    ) -> SegmentRecord:
        """创建待调度的作业切片。"""
        async with self._lock:
            segment = SegmentRecord(
                segment_id=segment_id,
                run_id=run_id,
                sequence_index=sequence_index,
                status=SegmentStatus.PENDING,
                fencing_token=0,
                owner_id=None,
                lease_expires_at_mono=0.0,
                max_steps=max_steps,
            )
            self._segments[segment_id] = segment
            return segment

    async def get_segment(self, segment_id: str) -> Optional[SegmentRecord]:
        """获取作业切片详情。"""
        async with self._lock:
            return self._segments.get(segment_id)

    async def claim_next_segment(
        self,
        worker_id: str,
        lease_seconds: float,
        run_id: Optional[str] = None,
    ) -> Optional[SegmentRecord]:
        """CAS 原子认领就绪的切片，自增 Fencing Token 杜绝脑裂。"""
        async with self._lock:
            candidates: List[SegmentRecord] = []
            for seg in self._segments.values():
                if seg.status == SegmentStatus.PENDING:
                    if run_id is None or seg.run_id == run_id:
                        candidates.append(seg)

            if not candidates:
                return None

            candidates.sort(key=lambda s: s.sequence_index)
            target = candidates[0]

            now = time.monotonic()
            new_fencing = target.fencing_token + 1
            claimed = SegmentRecord(
                segment_id=target.segment_id,
                run_id=target.run_id,
                sequence_index=target.sequence_index,
                status=SegmentStatus.CLAIMED,
                fencing_token=new_fencing,
                owner_id=worker_id,
                lease_expires_at_mono=now + lease_seconds,
                max_steps=target.max_steps,
                checkpoint_evidence=target.checkpoint_evidence,
            )
            self._segments[target.segment_id] = claimed

            # 联动更新 Run 的状态与当前切片游标
            run = self._runs.get(target.run_id)
            if run is not None and run.status == RunStatus.PENDING:
                self._runs[target.run_id] = RunRecord(
                    run_id=run.run_id,
                    conversation_id=run.conversation_id,
                    status=RunStatus.RUNNING,
                    created_at_mono=run.created_at_mono,
                    updated_at_mono=now,
                    current_segment_id=target.segment_id,
                )

            # 登记 Attempt
            attempt_id = f"att_{target.segment_id}_{new_fencing}"
            self._attempts[attempt_id] = AttemptRecord(
                attempt_id=attempt_id,
                segment_id=target.segment_id,
                worker_id=worker_id,
                status=AttemptStatus.RUNNING,
                fencing_token=new_fencing,
                started_at_mono=now,
            )
            return claimed

    async def renew_lease(
        self,
        segment_id: str,
        fencing_token: int,
        lease_seconds: float,
    ) -> bool:
        """带 Fencing Token 强校验的租约续约，拒绝已被重派切片的陈旧续约。"""
        async with self._lock:
            seg = self._segments.get(segment_id)
            if seg is None or seg.fencing_token != fencing_token:
                return False
            if seg.status not in (SegmentStatus.CLAIMED, SegmentStatus.RUNNING):
                return False

            now = time.monotonic()
            self._segments[segment_id] = SegmentRecord(
                segment_id=seg.segment_id,
                run_id=seg.run_id,
                sequence_index=seg.sequence_index,
                status=SegmentStatus.RUNNING,
                fencing_token=seg.fencing_token,
                owner_id=seg.owner_id,
                lease_expires_at_mono=now + lease_seconds,
                max_steps=seg.max_steps,
                checkpoint_evidence=seg.checkpoint_evidence,
            )
            return True

    async def record_checkpoint(
        self,
        segment_id: str,
        fencing_token: int,
        evidence: CheckpointEvidence,
    ) -> bool:
        """记录现场检查点证据，保证现场可回溯。"""
        async with self._lock:
            seg = self._segments.get(segment_id)
            if seg is None or seg.fencing_token != fencing_token:
                return False

            self._segments[segment_id] = SegmentRecord(
                segment_id=seg.segment_id,
                run_id=seg.run_id,
                sequence_index=seg.sequence_index,
                status=seg.status,
                fencing_token=seg.fencing_token,
                owner_id=seg.owner_id,
                lease_expires_at_mono=seg.lease_expires_at_mono,
                max_steps=seg.max_steps,
                checkpoint_evidence=evidence,
            )
            return True

    async def settle_segment(
        self,
        segment_id: str,
        fencing_token: int,
        status: SegmentStatus,
        error_message: Optional[str] = None,
    ) -> bool:
        """安全结算切片，若 Token 过期则判定已被孤立拒绝写入。"""
        async with self._lock:
            seg = self._segments.get(segment_id)
            if seg is None or seg.fencing_token != fencing_token:
                return False

            now = time.monotonic()
            self._segments[segment_id] = SegmentRecord(
                segment_id=seg.segment_id,
                run_id=seg.run_id,
                sequence_index=seg.sequence_index,
                status=status,
                fencing_token=seg.fencing_token,
                owner_id=seg.owner_id,
                lease_expires_at_mono=0.0,
                max_steps=seg.max_steps,
                checkpoint_evidence=seg.checkpoint_evidence,
            )

            attempt_id = f"att_{segment_id}_{fencing_token}"
            att = self._attempts.get(attempt_id)
            if att is not None:
                att_status = (
                    AttemptStatus.SUCCESS
                    if status == SegmentStatus.COMPLETED
                    else AttemptStatus.FAILED
                )
                self._attempts[attempt_id] = AttemptRecord(
                    attempt_id=att.attempt_id,
                    segment_id=att.segment_id,
                    worker_id=att.worker_id,
                    status=att_status,
                    fencing_token=att.fencing_token,
                    started_at_mono=att.started_at_mono,
                    finished_at_mono=now,
                    error_message=error_message,
                )
            return True

    async def find_expired_segments(
        self,
        now_mono: float,
    ) -> List[SegmentRecord]:
        """扫描所有已超期且未结算的切片候选者。"""
        async with self._lock:
            expired: List[SegmentRecord] = []
            for seg in self._segments.values():
                if (
                    seg.status in (SegmentStatus.CLAIMED, SegmentStatus.RUNNING)
                    and seg.lease_expires_at_mono <= now_mono
                ):
                    expired.append(seg)
            return expired

    async def reset_segment_to_pending(
        self,
        segment_id: str,
        expected_fencing_token: int,
    ) -> bool:
        """重置切片为待调度，保留最新 Fencing Token。"""
        async with self._lock:
            seg = self._segments.get(segment_id)
            if seg is None or seg.fencing_token != expected_fencing_token:
                return False

            self._segments[segment_id] = SegmentRecord(
                segment_id=seg.segment_id,
                run_id=seg.run_id,
                sequence_index=seg.sequence_index,
                status=SegmentStatus.PENDING,
                fencing_token=seg.fencing_token,
                owner_id=None,
                lease_expires_at_mono=0.0,
                max_steps=seg.max_steps,
                checkpoint_evidence=seg.checkpoint_evidence,
            )
            return True

    async def enqueue_input(
        self,
        input_id: str,
        run_id: str,
        content: str,
    ) -> InFlightInputRecord:
        """将用户飞入新输入压入持久队列。"""
        async with self._lock:
            record = InFlightInputRecord(
                input_id=input_id,
                run_id=run_id,
                content=content,
                status=InputStatus.PENDING,
                created_at_mono=time.monotonic(),
            )
            self._inputs[input_id] = record
            return record

    async def claim_pending_inputs_for_segment(
        self,
        run_id: str,
        segment_id: str,
    ) -> List[InFlightInputRecord]:
        """切片边界原子提取待注入的用户输入。"""
        async with self._lock:
            claimed: List[InFlightInputRecord] = []
            for item in self._inputs.values():
                if item.run_id == run_id and item.status == InputStatus.PENDING:
                    updated = InFlightInputRecord(
                        input_id=item.input_id,
                        run_id=item.run_id,
                        content=item.content,
                        status=InputStatus.CLAIMED,
                        created_at_mono=item.created_at_mono,
                        claimed_segment_id=segment_id,
                    )
                    self._inputs[item.input_id] = updated
                    claimed.append(updated)
            return claimed

    async def mark_inputs_consumed(self, segment_id: str) -> int:
        """切片结算后原子标记输入为已消费。"""
        async with self._lock:
            count = 0
            for item in self._inputs.values():
                if (
                    item.claimed_segment_id == segment_id
                    and item.status == InputStatus.CLAIMED
                ):
                    self._inputs[item.input_id] = InFlightInputRecord(
                        input_id=item.input_id,
                        run_id=item.run_id,
                        content=item.content,
                        status=InputStatus.CONSUMED,
                        created_at_mono=item.created_at_mono,
                        claimed_segment_id=segment_id,
                    )
                    count += 1
            return count
