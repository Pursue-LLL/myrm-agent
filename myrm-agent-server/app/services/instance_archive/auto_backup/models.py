"""Contracts of the scheduled whole-instance backup.

[INPUT]
- stdlib only

[OUTPUT]
- Frequency: how often a backup is due
- AutoBackupSettings: what the user chose (persisted)
- AutoBackupState: how the last attempts went (persisted); what is backed up is read from the folder
- BackupFile: one backup kept in the destination folder
- AutoBackupError: stable machine code of a failed run or an invalid destination
- KEEP_MIN / KEEP_MAX / DEFAULT_KEEP, BACKUP_NAME_PREFIX, INSTANCE_TAG_PATTERN

[POS]
Neutral data contracts shared by the store, the schedule rule, retention and the
runner. No I/O and no policy beyond the value bounds.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

KEEP_MIN = 1
KEEP_MAX = 10
DEFAULT_KEEP = 3
BACKUP_NAME_PREFIX = "myrm-auto-backup-"
INSTANCE_TAG_PATTERN = r"[0-9a-f]{8}"


class Frequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"

    @property
    def interval(self) -> timedelta:
        return timedelta(days=1 if self is Frequency.DAILY else 7)


@dataclass(frozen=True, slots=True)
class AutoBackupSettings:
    """``directory`` is None for the default folder inside the state directory."""

    enabled: bool = False
    frequency: Frequency = Frequency.DAILY
    keep: int = DEFAULT_KEEP
    directory: str | None = None


@dataclass(frozen=True, slots=True)
class AutoBackupState:
    """Whether the folder holds a backup is a fact of the folder, never recorded here."""

    last_attempt_at: datetime | None = None
    consecutive_failures: int = 0
    last_error_code: str | None = None


@dataclass(frozen=True, slots=True)
class BackupFile:
    name: str
    created_at: datetime
    size_bytes: int


class AutoBackupError(Exception):
    """A run or a destination was rejected; ``code`` is the stable reason the UI localizes."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
