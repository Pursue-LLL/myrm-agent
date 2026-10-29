"""本地到云沙箱的委派信封、跨端进度广播与成果回拉的包入口。

[INPUT]
- app.services.agent.workload_delegation.workload_handover_delegator (POS: 委派状态机与信封打包)
- app.services.agent.workload_delegation.live_progress_hud_hub (POS: 进度事件的发布 / 订阅与最新快照)
- app.services.agent.workload_delegation.offline_pullback_engine (POS: 云端成果回拉本地的冲突检测与合并)

[OUTPUT]
- WorkloadHandoverDelegator, DelegationEnvelope, DelegationState, PreflightCheckResult, DEFAULT_EXCLUDE_PATTERNS
- LiveProgressHudHub, StepProgressEvent
- OfflinePullbackEngine, PullbackBundle, PullbackApplyResult, MergeStatus

[POS]
一次委派的三个环节（打包移交、进度同步、成果回拉）作为同一个包导出。
"""

from __future__ import annotations

from app.services.agent.workload_delegation.live_progress_hud_hub import (
    LiveProgressHudHub,
    StepProgressEvent,
)
from app.services.agent.workload_delegation.offline_pullback_engine import (
    MergeStatus,
    OfflinePullbackEngine,
    PullbackApplyResult,
    PullbackBundle,
)
from app.services.agent.workload_delegation.workload_handover_delegator import (
    DEFAULT_EXCLUDE_PATTERNS,
    DelegationEnvelope,
    DelegationState,
    PreflightCheckResult,
    WorkloadHandoverDelegator,
)

__all__ = [
    "DEFAULT_EXCLUDE_PATTERNS",
    "DelegationEnvelope",
    "DelegationState",
    "LiveProgressHudHub",
    "MergeStatus",
    "OfflinePullbackEngine",
    "PreflightCheckResult",
    "PullbackApplyResult",
    "PullbackBundle",
    "StepProgressEvent",
    "WorkloadHandoverDelegator",
]
