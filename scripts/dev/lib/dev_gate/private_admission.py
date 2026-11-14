"""What the private admission queue stores and answers: its table layout and the result of an admit call."""

from __future__ import annotations

from dataclasses import dataclass

QUEUE_SCHEMA = """
CREATE TABLE IF NOT EXISTS private_admission (
    session_id TEXT PRIMARY KEY,
    owner_token TEXT NOT NULL,
    credits INTEGER NOT NULL,
    priority INTEGER NOT NULL,
    enqueued_at REAL NOT NULL,
    granted_at REAL,
    released_at REAL
);
CREATE INDEX IF NOT EXISTS private_admission_wait_idx
ON private_admission(granted_at, released_at, enqueued_at);
"""


@dataclass(frozen=True, slots=True)
class PrivateAdmission:
    granted: bool
    queue_position: int
    active_credits: int
    capacity_credits: int
    waited_sec: float
    next_progress_sec: float
    idle_reason: str = ""
    available_credits: int = 0
