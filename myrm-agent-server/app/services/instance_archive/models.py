"""Instance archive data contracts and on-disk layout.

[INPUT]
- pathlib / json: working-directory layout and JSON persistence

[OUTPUT]
- ArchivePaths: every working path of the feature under ``{state_dir}/instance_archive``
- Operation / PendingPromotion: the marker the next boot promotes
- PromotionOutcome: one-time result shown after the restart
- ImportReport: what a verified archive would change, shown before confirming

[POS]
Neutral contracts shared by export, import, restore points and the pre-boot
promotion hook. Contains no policy and no I/O beyond atomic JSON files.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Self


@dataclass(frozen=True, slots=True)
class ArchivePaths:
    """Working layout; lives on the same volume as the state dir so promotion is a rename."""

    state_dir: Path

    @property
    def root(self) -> Path:
        return self.state_dir / "instance_archive"

    @property
    def exports(self) -> Path:
        return self.root / "exports"

    @property
    def uploads(self) -> Path:
        return self.root / "uploads"

    @property
    def staging(self) -> Path:
        return self.root / "staging"

    @property
    def aside(self) -> Path:
        return self.root / "aside"

    @property
    def journal(self) -> Path:
        return self.root / "promotion.journal.json"

    @property
    def pending(self) -> Path:
        return self.root / "pending.json"

    @property
    def result(self) -> Path:
        return self.root / "last_result.json"


class Operation(StrEnum):
    IMPORT = "import"
    RESTORE_POINT = "restore_point"
    ROLLBACK = "rollback"


class OutcomeStatus(StrEnum):
    RESTORED = "restored"
    FAILED = "failed"
    WAITING = "waiting"  # requester process still alive; promotion deferred


def write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


@dataclass(frozen=True, slots=True)
class PendingPromotion:
    """Written by the running server, consumed by the next boot before any database opens."""

    operation: Operation
    staging_dir: str
    aside_dir: str
    entries: tuple[str, ...]
    requester_pid: int
    requester_started_at: float
    created_at: str
    summary: dict[str, int] = field(default_factory=dict)
    reentry: tuple[str, ...] = ()

    def save(self, path: Path) -> None:
        write_json_atomic(path, asdict(self))

    @classmethod
    def load(cls, path: Path) -> Self | None:
        raw = read_json(path)
        if raw is None:
            return None
        try:
            entries = raw["entries"]
            reentry = raw.get("reentry", [])
            summary = raw.get("summary", {})
            if not isinstance(entries, list) or not isinstance(reentry, list) or not isinstance(summary, dict):
                return None
            return cls(
                operation=Operation(str(raw["operation"])),
                staging_dir=str(raw["staging_dir"]),
                aside_dir=str(raw["aside_dir"]),
                entries=tuple(str(e) for e in entries),
                requester_pid=int(str(raw["requester_pid"])),
                requester_started_at=float(str(raw["requester_started_at"])),
                created_at=str(raw["created_at"]),
                summary={str(k): int(v) for k, v in summary.items() if isinstance(v, int)},
                reentry=tuple(str(r) for r in reentry),
            )
        except (KeyError, ValueError, TypeError):
            return None


@dataclass(frozen=True, slots=True)
class PromotionOutcome:
    operation: Operation
    status: OutcomeStatus
    completed_at: str
    summary: dict[str, int] = field(default_factory=dict)
    reentry: tuple[str, ...] = ()
    error_code: str | None = None
    rollback_available: bool = False

    def save(self, path: Path) -> None:
        write_json_atomic(path, asdict(self))

    @classmethod
    def load(cls, path: Path) -> Self | None:
        raw = read_json(path)
        if raw is None:
            return None
        try:
            summary = raw.get("summary", {})
            reentry = raw.get("reentry", [])
            if not isinstance(summary, dict) or not isinstance(reentry, list):
                return None
            error_code = raw.get("error_code")
            return cls(
                operation=Operation(str(raw["operation"])),
                status=OutcomeStatus(str(raw["status"])),
                completed_at=str(raw["completed_at"]),
                summary={str(k): int(v) for k, v in summary.items() if isinstance(v, int)},
                reentry=tuple(str(r) for r in reentry),
                error_code=None if error_code is None else str(error_code),
                rollback_available=bool(raw.get("rollback_available", False)),
            )
        except (KeyError, ValueError, TypeError):
            return None


@dataclass(frozen=True, slots=True)
class ImportReport:
    """What the staged archive would change; produced before the user confirms.

    ``created_at`` is when the backup was made; ``counts`` describe the backup and
    ``current_counts`` the same tables in the running instance (empty when unreadable).
    ``unreadable_count`` is how many items the export could not read, so the backup lacks them and a swap
    removes the running instance's copies.
    """

    session_id: str
    created_at: str
    counts: dict[str, int]
    current_counts: dict[str, int]
    executable: dict[str, int]
    reentry: tuple[str, ...]
    paused_jobs: int
    missing_paths: int
    unreadable_count: int
    identity_dropped: bool
    config_key_carried: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
