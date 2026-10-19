# -*- coding: utf-8 -*-
"""Live Transcript and Persistent Delegation Ledger for Subagents.

Provides transparent streaming execution telemetry, crash-durable background task
recovery, isolated single-command Smart Approvals with interactive /deny feedback,
and MoA dynamic reasoning intensity allocation.

[INPUT]
- Package re-exports only; no runtime input.

[OUTPUT]
- SubagentTranscriptEmitter, DelegationLedger, ReasoningEffortGovernor, SmartApprovalsGate and models.

[POS]
Public surface only; the emitter produces the transcript, the ledger persists delegation state.
"""

from .delegation_ledger import PersistentDelegationLedger
from .reasoning_governor import MoAReasoningEffortGovernor
from .smart_approvals import SmartApprovalGate
from .transcript_emitter import SubagentLiveTranscriptEmitter
from .types import (
    ApprovalDecision,
    DelegationTaskRecord,
    ReasoningEffortLevel,
    SmartApprovalRequest,
    SmartApprovalResolution,
    SubagentTranscriptEvent,
    TaskDelegationStatus,
    TranscriptEventKind,
)

__all__ = [
    "ApprovalDecision",
    "DelegationTaskRecord",
    "MoAReasoningEffortGovernor",
    "PersistentDelegationLedger",
    "ReasoningEffortLevel",
    "SmartApprovalGate",
    "SmartApprovalRequest",
    "SmartApprovalResolution",
    "SubagentLiveTranscriptEmitter",
    "SubagentTranscriptEvent",
    "TaskDelegationStatus",
    "TranscriptEventKind",
]
