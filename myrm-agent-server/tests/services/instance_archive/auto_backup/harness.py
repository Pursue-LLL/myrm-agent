"""A scheduled-backup service over a real state directory, with a settable clock.

[INPUT]
- app.services.instance_archive.auto_backup: the service under test, its settings and file naming
- app.services.instance_archive.auto_backup.folder_guard::FolderGuard (POS: bounded access to the user-chosen backup folder)
- app.services.instance_archive: the real export manager
- tests.services.instance_archive.auto_backup.rig::Clock (POS: a settable clock for the scheduled-backup tests)

[OUTPUT]
- ON: daily backups, three copies, default folder
- Harness: service + clock + the alerts it published; ``put`` drops a backup file into a folder, ``settled`` waits for a run
- until / scheduled_run_ends: wait for a condition, or for the scheduled run the tick starts to end, whatever its outcome

[POS]
Test harness of the scheduled-backup service: the real service and export manager over a real state directory,
so scheduling, failure back-off and alerts can be driven through time by moving the clock.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from app.services.instance_archive import ArchivePaths, ExportJobManager
from app.services.instance_archive.auto_backup import AutoBackupService, AutoBackupSettings, Frequency
from app.services.instance_archive.auto_backup.folder_guard import FolderGuard
from app.services.instance_archive.auto_backup.retention import backup_name, list_backups
from tests.services.instance_archive.auto_backup.rig import Clock

ON = AutoBackupSettings(enabled=True, frequency=Frequency.DAILY, keep=3, directory=None)


class Harness:
    def __init__(
        self, state: Path, *, folder_guard: FolderGuard | None = None, transfer_guard: FolderGuard | None = None
    ) -> None:
        self.paths = ArchivePaths(state)
        self.clock = Clock(datetime(2026, 10, 13, 3, 0, tzinfo=UTC))
        self.alerts: list[tuple[str, str]] = []
        self.service = AutoBackupService(
            paths=self.paths,
            manager=ExportJobManager(self.paths),
            app_version="1.0.0",
            deploy_mode="local",
            publish_alert=lambda code: self.alerts.append((code, threading.current_thread().name)),
            clock=self.clock,
            folder_guard=folder_guard,
            transfer_guard=transfer_guard,
        )

    @property
    def tag(self) -> str:
        return self.service._store.tag()

    def stored(self, folder: Path) -> list[str]:
        return [backup.name for backup in list_backups(folder, self.tag)]

    def put(self, folder: Path, moment: datetime, *, tag: str | None = None) -> Path:
        """A backup file as another run, or another instance sharing the folder, would have left it."""
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / backup_name(moment, tag or self.tag)
        path.write_bytes(b"x")
        return path

    async def settled(self, *, attempts: int = 1) -> None:
        """Wait until the background run has recorded ``attempts`` outcomes and released the runner."""
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            view = self.service.view()
            if (
                not view.running
                and view.state.last_attempt_at == self.clock.now
                and (
                    view.last is not None
                    and view.last.created_at == self.clock.now
                    or view.state.consecutive_failures >= attempts
                )
            ):
                await asyncio.sleep(0)  # the worker hands its alert to this loop with call_soon_threadsafe; let it run
                return
            await asyncio.sleep(0.1)
        raise AssertionError("background backup did not settle")


async def until(check: Callable[[], bool], what: str) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if check():
            await asyncio.sleep(0)  # a worker hands its alert to this loop with call_soon_threadsafe; let it run
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"{what} did not happen in time")


async def scheduled_run_ends(harness: Harness) -> None:
    assert await harness.service.tick()
    await until(lambda: not harness.service.view().running, "the scheduled run ending")
