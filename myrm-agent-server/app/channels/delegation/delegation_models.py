"""Pure data models for mobile-to-desktop cross-platform task delegation and delivery.

Strictly decoupled from concrete I/O, networking, and UI rendering.
Defines typed envelopes for asynchronous delegation, lifecycle status,
in-flight steering, remote approval relay, progress beacons, and artifacts.

[INPUT]
- Pure Python primitive types and standard dataclasses.

[OUTPUT]
- DelegationStatus: Enum of asynchronous task execution states.
- RiskLevel: Enum of operational security risk levels for approvals.
- DelegationTask: Core persistent task entity.
- DelegationReceipt: Immediate acknowledgement envelope returned to mobile client.
- SteeringMessage: In-flight user guidance injected into running task.
- ApprovalRequest: Remote authorization request payload sent to mobile.
- ApprovalResponse: User decision payload returned from mobile.
- DeliveryArtifact: Metadata descriptor for generated multi-modal deliverable.
- ProgressBeacon: Periodic execution heartbeat and milestone beacon.

[POS]
Domain contract SSOT for app/channels/delegation/ subsystem.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Literal


class DelegationStatus(str, enum.Enum):
    """Lifecycle states of an asynchronous delegated task."""

    PENDING = "pending"
    RUNNING = "running"
    SUSPENDED_FOR_APPROVAL = "suspended_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RiskLevel(str, enum.Enum):
    """Security risk severity for remote approval requests."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class DeliveryArtifact:
    """Descriptor for a file or deliverable produced during task execution."""

    file_name: str
    file_path: str
    file_size_bytes: int
    mime_type: str = "application/octet-stream"
    sha256_hash: str = ""
    is_oversized: bool = False
    direct_download_url: str = ""
    created_at: float = field(default_factory=time.time)


@dataclass
class ProgressBeacon:
    """Heartbeat milestone tracking progress of a delegated background task."""

    task_id: str
    phase: str
    percent: int
    milestone_message: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class DelegationReceipt:
    """Immediate acknowledgement returned to mobile caller in <1 second."""

    task_id: str
    status: DelegationStatus
    estimated_duration_seconds: int
    ack_message: str
    tracking_deep_link: str = ""
    created_at: float = field(default_factory=time.time)


@dataclass
class SteeringMessage:
    """In-flight prompt guidance dynamically appended by mobile user."""

    task_id: str
    content: str
    sender_id: str
    injected_at: float = field(default_factory=time.time)


@dataclass
class ApprovalRequest:
    """Authorization payload dispatched to mobile client when high-risk tool is invoked."""

    request_id: str
    task_id: str
    action_name: str
    action_summary: str
    risk_level: RiskLevel
    options: list[str] = field(default_factory=lambda: ["approve", "reject"])
    created_at: float = field(default_factory=time.time)
    timeout_seconds: float = 300.0


@dataclass
class ApprovalResponse:
    """User decision returned from mobile interactive card or numbered reply."""

    request_id: str
    task_id: str
    decision: Literal["approve", "reject"]
    responder_id: str
    responded_at: float = field(default_factory=time.time)
    note: str = ""


@dataclass
class DelegationTask:
    """Persistent entity representing a delegated asynchronous background task."""

    task_id: str
    origin_channel: str
    origin_user_id: str
    origin_chat_id: str
    raw_prompt: str
    normalized_prompt: str
    status: DelegationStatus = DelegationStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    error_message: str = ""
    result_summary: str = ""
    artifacts: list[DeliveryArtifact] = field(default_factory=list)
    timeout_seconds: float = 3600.0
    quiet_hours_scheduled_push: float | None = None
    metadata: dict[str, object] = field(default_factory=dict)
