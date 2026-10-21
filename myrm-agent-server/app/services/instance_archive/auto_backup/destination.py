"""Where scheduled backups are written, and whether that place is acceptable.

[INPUT]
- app.services.instance_archive.models::ArchivePaths (POS: state directory)
- app.services.instance_archive.auto_backup.models::AutoBackupError (POS: stable reason codes)
- app.services.instance_archive.auto_backup.folder_guard::FolderGuard, FolderUnresponsive (POS: bounded access to the user-chosen backup folder)

[OUTPUT]
- destination_path: the folder a setting points at (default: ``{state}/backups/instance``); a ``~user`` that cannot be resolved stays as typed
- prepare_destination: validate, create and probe that folder
- prepare_destination_guarded: the same through a ``FolderGuard``; a folder that does not answer is refused as unavailable

[POS]
A destination inside the state directory is only acceptable under ``backups/``,
which the archive policy classifies as local history: it is never carried into a
backup, so retained files neither nest into the next archive nor get swept or
swapped by an import. Any other place inside the state directory (live data,
the archive's own working folders) is refused. A folder outside it may be
anything the user can write to, including a synced or external drive. Whoever
prepares the folder for a save or a run does so through the guarded form, so a
share that stops answering is refused with a stable code instead of pinning the caller.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.services.instance_archive.auto_backup.folder_guard import FolderGuard, FolderUnresponsive
from app.services.instance_archive.auto_backup.models import AutoBackupError
from app.services.instance_archive.models import ArchivePaths

_LOCAL_HISTORY_DIR = "backups"
_DEFAULT_DIR = "instance"


def destination_path(paths: ArchivePaths, directory: str | None) -> Path:
    """Where a setting points; no validation and no filesystem change.

    A ``~user`` whose home cannot be determined stays as typed: it is not an absolute path, so preparing it refuses it.
    """
    if directory is None:
        return paths.state_dir / _LOCAL_HISTORY_DIR / _DEFAULT_DIR
    typed = Path(directory)
    try:
        return typed.expanduser()
    except RuntimeError:
        return typed


def prepare_destination(paths: ArchivePaths, directory: str | None) -> Path:
    """The resolved, existing, writable destination folder, or an ``AutoBackupError``."""
    target = destination_path(paths, directory)
    if not target.is_absolute():
        raise AutoBackupError("backup_dir_invalid", "The backup folder must be an absolute path")
    resolved = target.resolve()
    state = paths.state_dir.resolve()
    if _within(resolved, state) and not _within(resolved, state / _LOCAL_HISTORY_DIR):
        raise AutoBackupError("backup_dir_inside_state", "The backup folder must be outside the app data folder")
    try:
        resolved.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise AutoBackupError("backup_dir_invalid", f"The backup folder cannot be created: {exc}") from exc
    try:
        with tempfile.NamedTemporaryFile(dir=resolved, prefix=".write-probe-"):
            pass
    except OSError as exc:
        raise AutoBackupError("backup_dir_not_writable", f"The backup folder is not writable: {exc}") from exc
    return resolved


def prepare_destination_guarded(guard: FolderGuard, paths: ArchivePaths, directory: str | None) -> Path:
    """``prepare_destination`` bounded by ``guard``.

    A folder that does not answer is refused as ``backup_write_failed``, which asks the user to check the folder,
    not as ``backup_dir_not_writable``, which asks the user to choose another one.
    """
    try:
        return guard.call(lambda: prepare_destination(paths, directory))
    except FolderUnresponsive as exc:
        raise AutoBackupError("backup_write_failed", "The backup folder is not responding") from exc


def _within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents
