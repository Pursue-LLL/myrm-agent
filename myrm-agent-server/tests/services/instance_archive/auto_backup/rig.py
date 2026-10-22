"""Shared assembly of a scheduled-backup runner over a real state directory.

[INPUT]
- app.services.instance_archive.auto_backup: runner, store, settings contracts
- app.services.instance_archive.auto_backup.folder_guard::FolderGuard (POS: bounded access to the user-chosen backup folder)
- app.services.instance_archive.auto_backup.runner::TRANSFER_STALL_SECONDS (POS: how long a copy into the destination may go without taking in a piece before the run gives up on it)
- app.services.instance_archive: the real export manager

[OUTPUT]
- Clock: a settable clock for the scheduled-backup tests
- Rig / build_rig: runner + store + manager + the failure alerts it raised; ``stored`` lists this instance's backups; the
  preflight guard and the transfer guard can be replaced to bound a stalled folder in a test

[POS]
Test rig of the scheduled-backup runner: the real runner, store and export manager over a state directory,
with a settable clock and a record of the failure alerts it raised.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypedDict, Unpack

from app.services.instance_archive import ArchivePaths, ExportJobManager
from app.services.instance_archive.auto_backup import Frequency
from app.services.instance_archive.auto_backup.folder_guard import FolderGuard
from app.services.instance_archive.auto_backup.retention import list_backups
from app.services.instance_archive.auto_backup.runner import TRANSFER_STALL_SECONDS, AutoBackupRunner
from app.services.instance_archive.auto_backup.store import AutoBackupStore


class Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


class SettingChanges(TypedDict, total=False):
    frequency: Frequency
    keep: int
    directory: str | None


@dataclass
class Rig:
    paths: ArchivePaths
    store: AutoBackupStore
    manager: ExportJobManager
    runner: AutoBackupRunner
    clock: Clock
    alerts: list[str] = field(default_factory=list)

    @property
    def default_folder(self) -> Path:
        return self.paths.state_dir / "backups" / "instance"

    def stored(self, folder: Path | None = None) -> list[str]:
        """Names of this instance's backups in ``folder`` (default folder if omitted), newest first."""
        return [backup.name for backup in list_backups(folder or self.default_folder, self.store.tag())]

    def configure(self, **changes: Unpack[SettingChanges]) -> None:
        current, _ = self.store.load()
        self.store.save_settings(replace(current, enabled=True, **changes))


def build_rig(
    state: Path,
    *,
    manager: ExportJobManager | None = None,
    folder_guard: FolderGuard | None = None,
    transfer_guard: FolderGuard | None = None,
) -> Rig:
    paths = ArchivePaths(state)
    store = AutoBackupStore(paths)
    clock = Clock(datetime(2026, 10, 13, 3, 0, 0, tzinfo=UTC))
    alerts: list[str] = []
    shared = manager or ExportJobManager(paths)
    runner = AutoBackupRunner(
        paths=paths,
        store=store,
        manager=shared,
        folder_guard=folder_guard or FolderGuard(),
        transfer_guard=transfer_guard or FolderGuard(TRANSFER_STALL_SECONDS),
        app_version="1.0.0",
        deploy_mode="local",
        notify_failure=alerts.append,
        clock=clock,
    )
    rig = Rig(paths=paths, store=store, manager=shared, runner=runner, clock=clock, alerts=alerts)
    rig.configure()
    return rig
