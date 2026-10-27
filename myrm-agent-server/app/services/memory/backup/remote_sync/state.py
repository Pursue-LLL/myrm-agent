"""Persisted outcome of the scheduled remote memory backup, and the instance tag its files carry.

[INPUT]
- app.services.instance_archive.models::ArchivePaths, read_json, write_json_atomic (POS: layout + atomic JSON)
- app.services.instance_archive.auto_backup.store::AutoBackupStore (POS: the instance tag, shared by every backup of this instance)
- app.config.settings::get_settings (POS: the state directory of this instance)

[OUTPUT]
- RemoteSyncState: when the last backup succeeded, how the last attempt went, whether the user was told
- RemoteSyncStore: load / save the state; tag is this instance's marker in remote backup file names
- default_store: the store of this instance

[POS]
One JSON file under ``{state_dir}/instance_archive``. That directory is a runtime class of the archive policy, so an
instance backup never carries the file and an import never replaces it: a restore changes the data, never what the
schedule knows it has uploaded. Whether a backup is due comes from this file and not from the remote listing, because
a listing that cannot be read is indistinguishable from an empty folder. Unreadable or hostile content falls back to
defaults (a naive moment is read as UTC, counts are clamped), so a damaged file costs one early backup, never a
crash. Writers run on the event loop and every write replaces the file atomically. The tag is the one the whole-instance
backup uses: an instance has exactly one.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from app.config.settings import get_settings
from app.services.instance_archive.auto_backup.store import AutoBackupStore
from app.services.instance_archive.models import ArchivePaths, read_json, write_json_atomic

_FILE_NAME = "remote_memory_backup.json"


@dataclass(frozen=True, slots=True)
class RemoteSyncState:
    """``alerted`` is set once the user has been told about the current failure streak; a success clears it."""

    last_success_at: datetime | None = None
    last_attempt_at: datetime | None = None
    last_error_code: str | None = None
    consecutive_failures: int = 0
    alerted: bool = False

    def succeeded(self, now: datetime) -> RemoteSyncState:
        return RemoteSyncState(last_success_at=now, last_attempt_at=now)

    def failed(self, code: str, now: datetime) -> RemoteSyncState:
        return replace(
            self,
            last_attempt_at=now,
            last_error_code=code,
            consecutive_failures=self.consecutive_failures + 1,
        )

    def mark_alerted(self) -> RemoteSyncState:
        return replace(self, alerted=True)


class RemoteSyncStore:
    def __init__(self, paths: ArchivePaths) -> None:
        self._paths = paths
        self._file = paths.root / _FILE_NAME

    def load(self) -> RemoteSyncState:
        raw = read_json(self._file) or {}
        failures = raw.get("consecutive_failures")
        code = raw.get("last_error_code")
        return RemoteSyncState(
            last_success_at=_moment(raw.get("last_success_at")),
            last_attempt_at=_moment(raw.get("last_attempt_at")),
            last_error_code=code if isinstance(code, str) and code.strip() else None,
            consecutive_failures=max(failures, 0) if isinstance(failures, int) and not isinstance(failures, bool) else 0,
            alerted=raw.get("alerted") is True,
        )

    def save(self, state: RemoteSyncState) -> None:
        write_json_atomic(
            self._file,
            {
                "last_success_at": _iso(state.last_success_at),
                "last_attempt_at": _iso(state.last_attempt_at),
                "last_error_code": state.last_error_code,
                "consecutive_failures": state.consecutive_failures,
                "alerted": state.alerted,
            },
        )

    def tag(self) -> str:
        """This instance's marker in every remote backup file name; created on first use, then never changes."""
        return AutoBackupStore(self._paths).tag()


def default_store() -> RemoteSyncStore:
    return RemoteSyncStore(ArchivePaths(Path(get_settings().database.state_dir)))


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _moment(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
