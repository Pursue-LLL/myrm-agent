"""Naming, listing and pruning of the backups this instance wrote.

[INPUT]
- app.services.instance_archive.auto_backup.models (POS: neutral contracts: BackupFile, name prefix)

[OUTPUT]
- backup_name / incomplete_name: file name of a complete backup / of an incomplete copy made by an instance at a moment
- list_backups: the complete backups of one instance in a folder, newest first (OSError when the folder cannot be read)
- last_backup: the newest of those that is not dated after now
- prune: delete the oldest complete backups beyond ``keep``, incomplete copies a complete backup supersedes, and abandoned partial files
- prune_incomplete: keep only the newest incomplete copy and drop abandoned partial files; complete backups are never touched

[POS]
The destination folder may be shared with the user's own files and with other
instances of the app, so every operation here is confined to names that match this
instance's exact pattern (``myrm-auto-backup-{tag}-YYYYMMDD-HHMMSS.zip`` in UTC; an
incomplete copy is ``…-YYYYMMDD-HHMMSS.incomplete.zip``, which no complete-backup
pattern matches, so it is never counted, listed or kept as a backup).
Manual downloads, other archives, other instances' backups and symlinks are never
listed and never deleted. The folder is the only record of what has been backed up.
Pruning is only invoked after a new file has been written, and a run that produced
only an incomplete copy never touches a complete backup, so a failing run can never
shrink the set of copies the user has.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from app.services.instance_archive.auto_backup.models import BACKUP_NAME_PREFIX, BackupFile

logger = logging.getLogger(__name__)

_STAMP = r"(\d{8}-\d{6})"
_STAMP_FORMAT = "%Y%m%d-%H%M%S"
_COMPLETE = ".zip"
_INCOMPLETE = ".incomplete.zip"
_PARTIALS = (".zip.partial", ".incomplete.zip.partial")


def _own_pattern(tag: str, extension: str) -> re.Pattern[str]:
    return re.compile(rf"^{re.escape(BACKUP_NAME_PREFIX)}{re.escape(tag)}-{_STAMP}{re.escape(extension)}$")


def _stamped(moment: datetime, tag: str, extension: str) -> str:
    return f"{BACKUP_NAME_PREFIX}{tag}-{moment.astimezone(UTC).strftime(_STAMP_FORMAT)}{extension}"


def backup_name(moment: datetime, tag: str) -> str:
    return _stamped(moment, tag, _COMPLETE)


def incomplete_name(moment: datetime, tag: str) -> str:
    return _stamped(moment, tag, _INCOMPLETE)


def list_backups(directory: Path, tag: str) -> list[BackupFile]:
    """This instance's backups in ``directory``, newest first.

    Raises ``OSError`` when the folder cannot be read (drive unplugged, share offline, access denied): an
    unreadable folder says nothing about its backups, which is not the same as holding none.
    """
    entries = list(directory.iterdir())
    own = _own_pattern(tag, _COMPLETE)
    found: list[BackupFile] = []
    for entry in entries:
        match = own.match(entry.name)
        if match is None or entry.is_symlink():
            continue
        try:
            if not entry.is_file():
                continue
            size = entry.stat().st_size
            created = datetime.strptime(match.group(1), _STAMP_FORMAT).replace(tzinfo=UTC)
        except (OSError, ValueError):
            continue
        found.append(BackupFile(name=entry.name, created_at=created, size_bytes=size))
    return sorted(found, key=lambda backup: backup.created_at, reverse=True)


def last_backup(backups: Sequence[BackupFile], now: datetime) -> BackupFile | None:
    """The newest backup (``backups`` is newest first) that is not dated after ``now``.

    A file dated in the future comes from a clock that ran ahead and was corrected. It proves nothing
    about the data as of now, so it must neither postpone the next backup nor be shown as the last one.
    """
    return next((backup for backup in backups if backup.created_at <= now), None)


def prune(directory: Path, keep: int, tag: str, *, just_written: str) -> list[str]:
    """Remove complete backups beyond the newest ``keep``, incomplete copies, and partial files nobody is writing.

    A complete backup supersedes every incomplete copy: it holds all they do. ``just_written`` is never removed,
    whatever its date: a file dated in the future can outrank the new backup, and the run that just completed
    must not delete its own result. Returns removed names.
    """
    try:
        doomed = [backup.name for backup in list_backups(directory, tag)[keep:] if backup.name != just_written]
        doomed.extend(_own_files(directory, tag, _INCOMPLETE, *_PARTIALS))
    except OSError:
        return []
    return _remove(directory, doomed)


def prune_incomplete(directory: Path, tag: str, *, just_written: str) -> list[str]:
    """Keep only the incomplete copy ``just_written`` and remove partial files nobody is writing.

    Complete backups are never touched: a run that could not read everything must not cost the user a good copy.
    Returns removed names.
    """
    try:
        doomed = [name for name in _own_files(directory, tag, _INCOMPLETE) if name != just_written]
        doomed.extend(_own_files(directory, tag, *_PARTIALS))
    except OSError:
        return []
    return _remove(directory, doomed)


def _own_files(directory: Path, tag: str, *extensions: str) -> list[str]:
    patterns = [_own_pattern(tag, extension) for extension in extensions]
    return [entry.name for entry in directory.iterdir() if any(pattern.match(entry.name) for pattern in patterns)]


def _remove(directory: Path, names: Sequence[str]) -> list[str]:
    removed: list[str] = []
    for name in names:
        try:
            (directory / name).unlink()
        except FileNotFoundError:
            continue
        except OSError as exc:
            logger.warning("[AutoBackup] Could not remove old backup %s: %s", name, exc)
            continue
        removed.append(name)
    return removed
