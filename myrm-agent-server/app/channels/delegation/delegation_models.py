"""Pure data models for mobile-to-desktop cross-platform task delegation.

Strictly decoupled from concrete I/O, networking, and UI rendering.
Defines the typed task entity and lifecycle status of an asynchronous delegation.

[INPUT]
- Pure Python primitive types and standard dataclasses.

[OUTPUT]
- DelegationStatus: Enum of asynchronous task execution states.
- DelegationTask: Core task entity (held in memory by the coordinator).

[POS]
Domain contract SSOT for app/channels/delegation/ subsystem.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field


class DelegationStatus(str, enum.Enum):
    """Lifecycle states of an asynchronous delegated task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


@dataclass
class DelegationTask:
    """A delegated asynchronous background task; the coordinator holds it in memory until its outcome is handled."""

    task_id: str
    origin_channel: str
    origin_user_id: str
    origin_chat_id: str = ""
    prompt: str = ""
    status: DelegationStatus = DelegationStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    error_message: str = ""
    timeout_seconds: float = 3600.0
