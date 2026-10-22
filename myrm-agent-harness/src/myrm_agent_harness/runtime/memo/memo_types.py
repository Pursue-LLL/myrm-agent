"""Data contracts for the model-call memo ledger.

[INPUT]
- __future__
- dataclasses::dataclass
- enum::Enum

[OUTPUT]
- MemoStatus: the lifecycle state of one memoised model call
- MemoEntry: one recorded model call

[POS]
Framework-level types for the model-call memo ledger. A memo records what one model call
returned so that a repeated call with the same identity can read the answer back instead of
paying for the model a second time. Nothing here knows about chats, servers or providers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MemoStatus(str, Enum):
    """Lifecycle of a memoised model call.

    ``STARTED`` means the call was dispatched but its outcome is unknown — a crash left the
    row behind. Such a call is retried, because the model may or may not have been billed;
    only ``COMPLETED`` is replayed.
    """

    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class MemoEntry:
    """One memoised model call."""

    key: str
    status: MemoStatus
    model: str
    response: dict[str, object] | None
    created_at: float
    attempt: int
