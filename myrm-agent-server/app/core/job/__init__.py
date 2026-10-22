"""生产级作业系统模块。

提供 Run/Segment/Attempt 三层解耦模型、防脑裂 JobStore、租约心跳引擎、
四级现场求证对账器与切片边界输入摄入监督器。
"""

from __future__ import annotations

from app.core.job.lease_heartbeat import (
    LeaseContext,
    LeaseHeartbeatService,
    LeaseLostError,
)
from app.core.job.models import (
    AttemptRecord,
    AttemptStatus,
    CheckpointEvidence,
    InFlightInputRecord,
    InputStatus,
    ReconciliationAction,
    RunRecord,
    RunStatus,
    SegmentRecord,
    SegmentStatus,
)
from app.core.job.reconciliation import CheckpointReconciler
from app.core.job.store import JobStore
from app.core.job.supervisor import JobSupervisor

__all__ = [
    "RunStatus",
    "SegmentStatus",
    "AttemptStatus",
    "InputStatus",
    "ReconciliationAction",
    "CheckpointEvidence",
    "InFlightInputRecord",
    "AttemptRecord",
    "SegmentRecord",
    "RunRecord",
    "JobStore",
    "LeaseLostError",
    "LeaseHeartbeatService",
    "LeaseContext",
    "CheckpointReconciler",
    "JobSupervisor",
]
