"""Types for raw corpus deduplication governance.

[INPUT]
- (none: dataclasses, enums and one Protocol)

[OUTPUT]
- DedupTier, GroupStatus, DispositionAction: enums for tiers, group lifecycle and user decisions
- RawFileFingerprint, PlannedGroup, DuplicateGroup, DuplicateMember, DuplicateMemberSnippet: scan and review values
- HeldFile, FileEnqueuer: compile-hold row and the Protocol a release hands files to
- ScanProgress, ScanResult, DedupStats, DispositionResult, ExcludedRawEntry, TrashedRawEntry, VaultHygieneSnapshot

[POS]
Value contracts shared by scanner, store, governor and the server bridge: plain data plus the ``FileEnqueuer``
Protocol, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol


class DedupTier(StrEnum):
    """Duplicate detection tier."""

    EXACT = "exact"
    NORMALIZED = "normalized"
    NEAR = "near"


class DispositionAction(StrEnum):
    """User disposition for a duplicate group."""

    TRASH = "trash"
    EXCLUDE = "exclude"
    DISMISS = "dismiss"
    DEFER = "defer"


class GroupStatus(StrEnum):
    """Review status for a duplicate group."""

    OPEN = "open"
    DEFERRED = "deferred"
    RESOLVED = "resolved"


@dataclass(frozen=True, slots=True)
class RawFileFingerprint:
    """Fingerprints collected for one raw file."""

    relative_path: str
    exact_hash: str
    normalized_hash: str
    simhash: int
    size_bytes: int
    mtime_ns: int


@dataclass(frozen=True, slots=True)
class DuplicateMember:
    """One member of a duplicate group."""

    relative_path: str
    size_bytes: int
    mtime_ns: int


@dataclass(frozen=True, slots=True)
class DuplicateMemberSnippet:
    """Comparable body snippet for duplicate review."""

    relative_path: str
    snippet: str


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    """A cluster of potentially duplicate raw files."""

    group_id: int
    tier: DedupTier
    fingerprint: str
    recommended_keep_path: str
    status: GroupStatus
    members: tuple[DuplicateMember, ...]


@dataclass(frozen=True, slots=True)
class PlannedGroup:
    """A duplicate group a scan has worked out and not stored yet."""

    tier: DedupTier
    fingerprint: str
    recommended_keep_path: str
    members: tuple[DuplicateMember, ...]
    status: GroupStatus = GroupStatus.OPEN

    @property
    def member_paths(self) -> frozenset[str]:
        return frozenset(member.relative_path for member in self.members)


@dataclass(frozen=True, slots=True)
class HeldFile:
    """A raw file kept out of the compile queue until a scan that started after ``held_at_ns`` has looked at it."""

    relative_path: str
    held_at_ns: int


class FileEnqueuer(Protocol):
    """What a hold release needs from a compiler: queue one raw file for compiling."""

    def enqueue_file(self, file_path: Path) -> None: ...


@dataclass(frozen=True, slots=True)
class ScanProgress:
    """Incremental scan progress snapshot."""

    phase: Literal["idle", "scanning", "grouping", "done", "failed"] = "idle"
    files_scanned: int = 0
    files_total: int = 0
    groups_found: int = 0
    message: str = ""


@dataclass(frozen=True, slots=True)
class ScanResult:
    """Outcome of a corpus dedup scan."""

    files_scanned: int
    groups_found: int
    open_groups: int
    exact_groups: int
    normalized_groups: int
    near_groups: int
    duration_ms: int
    incremental: bool = False


@dataclass(frozen=True, slots=True)
class DispositionResult:
    """Outcome of applying a disposition to one group."""

    group_id: int
    action: DispositionAction
    affected_paths: tuple[str, ...] = field(default_factory=tuple)
    compile_jobs_prevented: int = 0


@dataclass(frozen=True, slots=True)
class DedupStats:
    """Overview stats for Settings / API."""

    duplicate_groups_pending: int
    compile_jobs_prevented: int
    eligible_raw_count: int
    excluded_raw_count: int
    trashed_raw_count: int


@dataclass(frozen=True, slots=True)
class TrashedRawEntry:
    """One raw file moved to corpus trash."""

    relative_path: str
    trash_relpath: str
    content_hash: str
    created_at: str


@dataclass(frozen=True, slots=True)
class ExcludedRawEntry:
    """One raw file excluded from compile via dedup disposition."""

    relative_path: str
    reason: str
    created_at: str


@dataclass(frozen=True, slots=True)
class VaultHygieneSnapshot:
    """Trashed and excluded raw paths for Settings review."""

    trashed: tuple[TrashedRawEntry, ...]
    excluded: tuple[ExcludedRawEntry, ...]
