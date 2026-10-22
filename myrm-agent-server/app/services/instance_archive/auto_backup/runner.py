"""One scheduled backup: export, place at the destination, check, record, prune.

[INPUT]
- app.services.instance_archive.export_jobs::ExportJobManager (POS: background export jobs, one at a time, shared with the manual flow)
- app.services.instance_archive.auto_backup.destination::destination_path, prepare_destination_guarded (POS: validates, creates and probes the backup folder; one that does not answer is refused)
- app.services.instance_archive.auto_backup.folder_guard::FolderGuard, FolderUnresponsive, Pulse (POS: bounded access to the user-chosen backup folder; a long transfer is waited for while it reports progress)
- app.services.instance_archive.auto_backup.retention::backup_name, incomplete_name, prune, prune_incomplete (POS: naming and pruning confined to this instance's own files)
- app.services.instance_archive.auto_backup.schedule::ALERT_AFTER_FAILURES (POS: pure due/overdue rules and the alert threshold)
- app.services.instance_archive.auto_backup.store::AutoBackupStore (POS: settings, run state and instance tag persisted outside the archive)
- app.services.instance_archive.auto_backup.models (POS: neutral contracts shared by every module here)
- app.core.security.auth.identity::LOCAL_USER_ID (POS: identity of every local-mode export)
- myrm_agent_harness.infra.state_archive::read_manifest, ensure_free_space (POS: structure-only archive read and free-space precheck)

[OUTPUT]
- AutoBackupRunner: run (one backup; failures are recorded, not raised), running
- TRANSFER_STALL_SECONDS: how long a copy into the destination may go without taking in a piece before the run gives up on it

[POS]
Reuses the exact export pipeline of the manual "Create backup" flow, so a scheduled
archive is byte-for-byte the same kind of file and restores through the same import
card. It never carries secrets (no passphrase, no config key). The archive is
produced in the archive working folder, synced to disk, then moved into the
destination (rename on one volume; copy to a ``.partial`` file, sync, rename across
volumes), so a backup name only ever appears for a complete file.

A run counts as completed only when the file is placed, its manifest reads back, its
size matches and the export left nothing out. That proves "written, structurally
readable and whole", not a full payload hash check: restore-time verification remains
the authority. The completed file itself is the record of success; only attempts and
failures are persisted. An export that could not read carried paths (``unreadable``) is
a recorded failure, ``backup_incomplete``: its archive is still stored, under an
incomplete-copy name that retention never counts as a backup, so the user can restore
what it holds while the failure and its alert stay visible. Only the newest incomplete
copy is kept, and it never costs a complete backup.
Retention of complete backups runs only after a completed run. A manual export in
flight makes ``run`` raise ``ExportBusyError`` without recording a failure. A failure
that belongs to a folder the user has since replaced is dropped, not charged to the
new folder; which folder is selected is told from the setting alone, never by touching
the folder.
Every access to the destination goes through a folder guard, so a share that stops
answering ends the attempt as a recorded failure instead of pinning the run: the next
attempts, the alert and the recovery follow the usual back-off. The preflight and the
retention sweep are short calls with the guard's short timeout; a sweep that does not
return is only logged, because the backup it follows is complete. Moving the archive in
and reading it back is one guarded transfer of its own. The copy syncs to the destination
every ``_SYNC_EVERY`` bytes, so a share that holds writes back until asked to flush them
still reports progress as it takes the data in, and the transfer is given up on only after
``TRANSFER_STALL_SECONDS`` without a piece being taken: a share that keeps taking data is
never cut off, however long the whole copy lasts. The copy that was given up on cannot be
stopped from outside; it stops at its next read or publish step, removes its ``.partial``
file and publishes nothing, so a recorded transfer failure never leaves a new file behind.
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from myrm_agent_harness.infra.state_archive import (
    ArchiveVerificationError,
    InsufficientSpaceError,
    ensure_free_space,
    read_manifest,
)

from app.core.security.auth.identity import LOCAL_USER_ID
from app.services.instance_archive.auto_backup.destination import destination_path, prepare_destination_guarded
from app.services.instance_archive.auto_backup.folder_guard import FolderGuard, FolderUnresponsive, Pulse
from app.services.instance_archive.auto_backup.models import AutoBackupError, AutoBackupState
from app.services.instance_archive.auto_backup.retention import backup_name, incomplete_name, prune, prune_incomplete
from app.services.instance_archive.auto_backup.schedule import ALERT_AFTER_FAILURES
from app.services.instance_archive.auto_backup.store import AutoBackupStore
from app.services.instance_archive.export_jobs import ExportBusyError, ExportJob, ExportJobManager
from app.services.instance_archive.models import ArchivePaths

logger = logging.getLogger(__name__)

_COPY_BUFFER = 1 << 20

# A share may hold written data back until it is asked to flush it (an NFS client does). Syncing after this many bytes
# keeps every flush short enough to count as progress, instead of leaving the whole archive to one silent call at the end.
_SYNC_EVERY = 64 << 20

# A share that takes in less than ``_SYNC_EVERY`` in this long (about 0.2 MiB/s) is treated as gone. One that keeps taking
# data is never cut off, however long the whole copy lasts.
TRANSFER_STALL_SECONDS = 300.0


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AutoBackupRunner:
    def __init__(
        self,
        *,
        paths: ArchivePaths,
        store: AutoBackupStore,
        manager: ExportJobManager,
        folder_guard: FolderGuard,
        transfer_guard: FolderGuard,
        app_version: str,
        deploy_mode: str,
        notify_failure: Callable[[str], None],
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._paths = paths
        self._store = store
        self._manager = manager
        self._folder = folder_guard
        self._transfer = transfer_guard
        self._app_version = app_version
        self._deploy_mode = deploy_mode
        self._notify_failure = notify_failure
        self._clock = clock
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._lock.locked()

    def run(self) -> AutoBackupState:
        """Make one backup now and return the recorded state. Raises ``ExportBusyError`` if another export runs."""
        if not self._lock.acquire(blocking=False):
            raise ExportBusyError("A scheduled backup is already running")
        try:
            return self._run_locked()
        finally:
            self._lock.release()

    def _run_locked(self) -> AutoBackupState:
        settings, _ = self._store.load()
        tag = self._store.tag()
        started = self._clock()
        target = destination_path(self._paths, settings.directory)
        try:
            destination = prepare_destination_guarded(self._folder, self._paths, settings.directory)
        except AutoBackupError as exc:
            logger.warning("[AutoBackup] The backup folder is not usable: %s", exc)
            return self._record_failure(exc.code, started, target)
        job = self._manager.start(
            user_id=LOCAL_USER_ID,
            app_version=self._app_version,
            deploy_mode=self._deploy_mode,
            config_key=None,
            passphrase=None,
        )
        try:
            job.done.wait()
            final, size, incomplete = self._place(job, destination, started, tag)
        except AutoBackupError as exc:
            return self._record_failure(exc.code, started, target)
        except InsufficientSpaceError:
            return self._record_failure("insufficient_space", started, target)
        except ArchiveVerificationError:
            return self._record_failure("backup_unreadable", started, target)
        except OSError:
            logger.exception("[AutoBackup] Could not write the backup")
            return self._record_failure("backup_write_failed", started, target)
        finally:
            self._discard(job)
        if incomplete:
            logger.warning("[AutoBackup] Kept an incomplete copy, some items could not be read: %s (%d bytes)", final.name, size)
            self._prune_incomplete(destination, tag, final.name)
            return self._record_failure("backup_incomplete", started, target)
        completed = AutoBackupState(last_attempt_at=started)
        self._store.save_state(completed)
        logger.info("[AutoBackup] Backup completed: %s (%d bytes)", final.name, size)
        self._prune(destination, settings.keep, tag, final.name)
        return completed

    def _discard(self, job: ExportJob) -> None:
        try:
            self._manager.discard(job.job_id)
        except OSError as exc:
            # A copy that was given up on may still hold the archive open, which blocks its removal on Windows. The
            # recorded outcome stands, and the export sweep removes the leftover once it is old enough.
            logger.warning("[AutoBackup] Could not remove the export archive: %s", exc)

    def _prune(self, destination: Path, keep: int, tag: str, just_written: str) -> None:
        try:
            self._folder.call(lambda: prune(destination, keep, tag, just_written=just_written))
        except FolderUnresponsive:
            logger.warning("[AutoBackup] The backup is complete, but the folder stopped answering during the cleanup")

    def _prune_incomplete(self, destination: Path, tag: str, just_written: str) -> None:
        try:
            self._folder.call(lambda: prune_incomplete(destination, tag, just_written=just_written))
        except FolderUnresponsive:
            logger.warning("[AutoBackup] The incomplete copy is stored, but the folder stopped answering during the cleanup")

    def _place(self, job: ExportJob, destination: Path, started: datetime, tag: str) -> tuple[Path, int, bool]:
        """Store the export under the name of what it is; the last item says whether it left carried paths out."""
        archive = self._manager.archive_path(job)
        result = job.result
        if archive is None or result is None:
            raise AutoBackupError(job.error_code or "export_failed", "The export did not complete")
        incomplete = bool(result.unreadable)
        size = archive.stat().st_size
        _sync_to_disk(archive)
        name = incomplete_name(started, tag) if incomplete else backup_name(started, tag)
        final = destination / name
        self._transfer.call_progressing(lambda pulse: _store(archive, final, size, pulse))
        return final, size, incomplete

    def _record_failure(self, code: str, at: datetime, target: Path) -> AutoBackupState:
        settings, state = self._store.load()
        if destination_path(self._paths, settings.directory) != target:
            logger.info("[AutoBackup] Dropped a failure (%s) of a folder that is no longer selected", code)
            return state
        failed = replace(state, last_attempt_at=at, consecutive_failures=state.consecutive_failures + 1, last_error_code=code)
        self._store.save_state(failed)
        logger.warning("[AutoBackup] Backup failed (%s), %d in a row", code, failed.consecutive_failures)
        if failed.consecutive_failures == ALERT_AFTER_FAILURES:
            self._notify_failure(code)
        return failed


def _sync_to_disk(path: Path) -> None:
    with path.open("rb+") as handle:
        os.fsync(handle.fileno())


def _same_volume(first: Path, second: Path) -> bool:
    return first.stat().st_dev == second.stat().st_dev


class _ProgressReader:
    """Reports progress before each chunk is read: the next read comes only after the previous write has returned."""

    __slots__ = ("_pulse", "_reader")

    def __init__(self, reader: IO[bytes], pulse: Pulse) -> None:
        self._reader = reader
        self._pulse = pulse

    def read(self, size: int = -1) -> bytes:
        self._pulse.progress()
        return self._reader.read(size)


class _SyncingWriter:
    """Syncs to the destination after every ``_SYNC_EVERY`` bytes; the next read then reports that sync as progress."""

    __slots__ = ("_pending", "_writer")

    def __init__(self, writer: IO[bytes]) -> None:
        self._writer = writer
        self._pending = 0

    def write(self, data: bytes) -> int:
        written = self._writer.write(data)
        self._pending += written
        if self._pending >= _SYNC_EVERY:
            _sync(self._writer)
            self._pending = 0
        return written


def _sync(writer: IO[bytes]) -> None:
    writer.flush()
    os.fsync(writer.fileno())


def _store(source: Path, final: Path, size: int, pulse: Pulse) -> None:
    """Put a whole, readable copy of ``source`` at ``final``, or leave nothing there.

    Runs under the transfer guard: ``pulse`` reports progress, and raises once the run has been given up on, so a
    copy that wakes up late publishes nothing and takes back what it already published.
    """
    _move(source, final, size, pulse)
    try:
        read_manifest(final)
        if final.stat().st_size != size:
            raise AutoBackupError("backup_unreadable", "The stored backup differs in size from the export")
        pulse.progress()
    except Exception:
        # A file that carries one of our names must read back as a whole archive: retention and restore trust the name.
        final.unlink(missing_ok=True)
        raise


def _move(source: Path, final: Path, size: int, pulse: Pulse) -> None:
    """Make ``final`` appear complete: a rename on one volume, a synced copy then a rename across volumes."""
    pulse.progress()
    if _same_volume(source, final.parent):
        pulse.progress()
        os.replace(source, final)
        return
    ensure_free_space(final.parent, size)
    partial = final.with_name(final.name + ".partial")
    try:
        with source.open("rb") as reader, partial.open("wb") as writer:
            shutil.copyfileobj(_ProgressReader(reader, pulse), _SyncingWriter(writer), _COPY_BUFFER)
            _sync(writer)
        pulse.progress()
        os.replace(partial, final)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
