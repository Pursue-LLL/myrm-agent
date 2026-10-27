"""Persistence of the auto backup settings, run state and instance tag.

[INPUT]
- app.services.instance_archive.models::ArchivePaths, read_json, write_json_atomic (POS: layout + atomic JSON)
- app.services.instance_archive.auto_backup.models (POS: contracts)

[OUTPUT]
- AutoBackupStore: load / save_settings / save_state persist the schedule; tag is this instance's marker in backup file names

[POS]
Two JSON files under ``{state_dir}/instance_archive``. That directory is a runtime
class of the archive policy, so neither file travels inside a backup or is touched
by an import: a restore changes the data, never the schedule that protects it, nor
the tag that marks which backups belong to this instance (the remote memory backup
marks its files with the same tag). Settings and state share one file that is
rewritten as a whole under a lock, so the API thread (settings) and the runner thread
(state) never lose each other's update; unreadable or hostile content falls back to
defaults and the counts are clamped into the allowed bounds, while a recorded moment
is kept as written (the schedule rules decide what a moment dated in the future is
worth). The tag lives in its own file, written once and never by a settings or state
save, so a read that fails on the settings can neither mint a new tag nor rewrite the
settings. One lock serves every store, so stores first used at the same moment still
agree on a single tag.
"""

from __future__ import annotations

import json
import re
import secrets
import threading
from datetime import UTC, datetime

from app.services.instance_archive.auto_backup.models import (
    DEFAULT_KEEP,
    INSTANCE_TAG_PATTERN,
    KEEP_MAX,
    KEEP_MIN,
    AutoBackupSettings,
    AutoBackupState,
    Frequency,
)
from app.services.instance_archive.models import ArchivePaths, read_json, write_json_atomic

_FILE_NAME = "auto_backup.json"
_TAG_FILE_NAME = "auto_backup_instance.json"
_TAG_BYTES = 4  # hex-encoded to the length INSTANCE_TAG_PATTERN accepts
_TAG_LOCK = threading.Lock()  # the tag file belongs to the instance, not to one store object


class AutoBackupStore:
    def __init__(self, paths: ArchivePaths) -> None:
        self._file = paths.root / _FILE_NAME
        self._tag_file = paths.root / _TAG_FILE_NAME
        self._lock = threading.Lock()

    def load(self) -> tuple[AutoBackupSettings, AutoBackupState]:
        with self._lock:
            return self._read()

    def save_settings(self, settings: AutoBackupSettings) -> None:
        with self._lock:
            _, state = self._read()
            self._write(settings, state)

    def save_state(self, state: AutoBackupState) -> None:
        with self._lock:
            settings, _ = self._read()
            self._write(settings, state)

    def tag(self) -> str:
        """The marker of this instance in its backup file names; created on first use, then never changes.

        Backups are told apart by the tag, not by a host name, so two instances that share one folder
        (a synced drive, a NAS share) never count or prune each other's files, even on identical hosts.
        """
        with _TAG_LOCK:
            tag = self._read_tag()
            if tag is None:
                tag = secrets.token_hex(_TAG_BYTES)
                write_json_atomic(self._tag_file, {"tag": tag})
            return tag

    def _read_tag(self) -> str | None:
        try:
            raw = json.loads(self._tag_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return None  # absent or damaged; any other read error propagates rather than minting a second tag
        return _parse_tag(raw.get("tag")) if isinstance(raw, dict) else None

    def _read(self) -> tuple[AutoBackupSettings, AutoBackupState]:
        raw = read_json(self._file) or {}
        return _parse_settings(raw.get("settings")), _parse_state(raw.get("state"))

    def _write(self, settings: AutoBackupSettings, state: AutoBackupState) -> None:
        write_json_atomic(
            self._file,
            {
                "settings": {
                    "enabled": settings.enabled,
                    "frequency": settings.frequency.value,
                    "keep": settings.keep,
                    "directory": settings.directory,
                },
                "state": {
                    "last_attempt_at": _iso(state.last_attempt_at),
                    "consecutive_failures": state.consecutive_failures,
                    "last_error_code": state.last_error_code,
                },
            },
        )


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _as_dict(raw: object) -> dict[str, object]:
    return raw if isinstance(raw, dict) else {}


def _int(raw: object) -> int | None:
    return raw if isinstance(raw, int) and not isinstance(raw, bool) else None


def _text(raw: object) -> str | None:
    return raw if isinstance(raw, str) and raw.strip() else None


def _moment(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _frequency(raw: object) -> Frequency:
    try:
        return Frequency(str(raw))
    except ValueError:
        return Frequency.DAILY


def _parse_settings(raw: object) -> AutoBackupSettings:
    data = _as_dict(raw)
    keep = _int(data.get("keep"))
    return AutoBackupSettings(
        enabled=data.get("enabled") is True,
        frequency=_frequency(data.get("frequency")),
        keep=DEFAULT_KEEP if keep is None else min(max(keep, KEEP_MIN), KEEP_MAX),
        directory=_text(data.get("directory")),
    )


def _parse_tag(raw: object) -> str | None:
    return raw if isinstance(raw, str) and re.fullmatch(INSTANCE_TAG_PATTERN, raw) else None


def _parse_state(raw: object) -> AutoBackupState:
    data = _as_dict(raw)
    failures = _int(data.get("consecutive_failures"))
    return AutoBackupState(
        last_attempt_at=_moment(data.get("last_attempt_at")),
        consecutive_failures=max(failures or 0, 0),
        last_error_code=_text(data.get("last_error_code")),
    )
