"""作业系统核心数据模型与状态机定义。

本模块提供 Run / Segment / Attempt 三层解耦状态定义与现场求证对账数据结构，
严格遵循类型完备性约束（严禁 Any 类型）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class RunStatus(str, Enum):
    """顶层 Run 状态机。"""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PAUSED_FOR_APPROVAL = "PAUSED_FOR_APPROVAL"
    CANCELED = "CANCELED"


class SegmentStatus(str, Enum):
    """切片级 Segment 状态机。"""

    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class AttemptStatus(str, Enum):
    """单次尝试 Attempt 执行状态机。"""

    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class InputStatus(str, Enum):
    """飞入输入队列状态。"""

    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    CONSUMED = "CONSUMED"


class ReconciliationAction(str, Enum):
    """四级现场求证对账处置动作。"""

    RETRY_SAFE = "RETRY_SAFE"
    RESUME_FROM_EVIDENCE = "RESUME_FROM_EVIDENCE"
    RECONCILE_MESSAGE = "RECONCILE_MESSAGE"
    BLOCK_UNCERTAIN_SIDE_EFFECT = "BLOCK_UNCERTAIN_SIDE_EFFECT"


@dataclass(frozen=True)
class CheckpointEvidence:
    """现场证据快照，用于超时求证对账。"""

    last_tool_name: Optional[str] = None
    has_side_effect: bool = False
    external_message_id: Optional[str] = None
    persisted_state_digest: Optional[str] = None
    step_index: int = 0
    extra_metadata: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class InFlightInputRecord:
    """飞行中的用户输入记录。"""

    input_id: str
    run_id: str
    content: str
    status: InputStatus
    created_at_mono: float
    claimed_segment_id: Optional[str] = None


@dataclass(frozen=True)
class AttemptRecord:
    """尝试记录，绑定物理执行者与时限。"""

    attempt_id: str
    segment_id: str
    worker_id: str
    status: AttemptStatus
    fencing_token: int
    started_at_mono: float
    finished_at_mono: Optional[float] = None
    error_message: Optional[str] = None


@dataclass(frozen=True)
class SegmentRecord:
    """作业切片记录，持有防脑裂栅栏令牌与租约时限。"""

    segment_id: str
    run_id: str
    sequence_index: int
    status: SegmentStatus
    fencing_token: int
    owner_id: Optional[str] = None
    lease_expires_at_mono: float = 0.0
    max_steps: int = 20
    checkpoint_evidence: Optional[CheckpointEvidence] = None


@dataclass(frozen=True)
class RunRecord:
    """顶层运行记录，对应一次长任务生命周期。"""

    run_id: str
    conversation_id: str
    status: RunStatus
    created_at_mono: float
    updated_at_mono: float
    current_segment_id: Optional[str] = None
    final_output: Optional[str] = None
    error_message: Optional[str] = None
