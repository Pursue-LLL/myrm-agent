"""Scheduled whole-instance backup as the API and the scheduler use it.

[INPUT]
- app.services.instance_archive.auto_backup.runner::AutoBackupRunner (POS: one scheduled backup, failures recorded not raised)
- app.services.instance_archive.auto_backup.store::AutoBackupStore (POS: settings, run state and instance tag persisted outside the archive)
- app.services.instance_archive.auto_backup.schedule::reference_moment, is_due, is_overdue (POS: pure due/overdue rules)
- app.services.instance_archive.auto_backup.destination::prepare_destination_guarded, destination_path (POS: validates, creates and probes the backup folder; one that does not answer is refused)
- app.services.instance_archive.auto_backup.retention::list_backups, last_backup (POS: naming and pruning confined to this instance's own files)
- app.services.instance_archive.auto_backup.folder_guard::FolderGuard (POS: bounded access to the user-chosen backup folder)
- app.services.instance_archive.export_jobs::get_export_manager (POS: background export jobs, one at a time, shared with the manual flow)
- app.services.event.app_event_bus::get_event_bus (POS: HEALTH_ALERT fan-out to the UI, IM and push)
- app.config: sandbox flag, state directory, app version, deploy mode (POS: deployment facts of this instance)

[OUTPUT]
- AutoBackupService: get_view / apply / start_run / tick
- AutoBackupView: settings + state + whether the folder can be read, due/overdue, the instance's backups in it and the last one
- get_auto_backup_service: the service of this instance, or None where it is not offered
- run_auto_backup_tick: the scheduler entry point (never raises)
- ALERT_COMPONENT: ``component`` of the HEALTH_ALERT event

[POS]
The runner executes in a daemon thread; the scheduler and the API only start it and
read the recorded state. The event bus is not thread-safe, so the alert is handed
back to the event loop that started the run. The backup folder is listed, created and
probed only through one folder guard shared with the runner: a share that stops
answering reads as unreadable, refuses a save or a manual run and ends a scheduled
attempt as a recorded failure, instead of pinning the threads the rest of the app
shares. The runner moves the archive in through a guard of its own, so a long copy never
queues these short calls behind it. Local and desktop instances only: a cloud sandbox
keeps its data on a managed volume, so the service is not offered there.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.config.deploy_mode import get_deploy_mode, is_sandbox
from app.config.settings import get_settings
from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus
from app.services.instance_archive.auto_backup.destination import destination_path, prepare_destination_guarded
from app.services.instance_archive.auto_backup.folder_guard import FolderGuard
from app.services.instance_archive.auto_backup.models import AutoBackupSettings, AutoBackupState, BackupFile
from app.services.instance_archive.auto_backup.retention import last_backup, list_backups
from app.services.instance_archive.auto_backup.runner import TRANSFER_STALL_SECONDS, AutoBackupRunner
from app.services.instance_archive.auto_backup.schedule import is_due, is_overdue, reference_moment
from app.services.instance_archive.auto_backup.store import AutoBackupStore
from app.services.instance_archive.export_jobs import ExportBusyError, ExportJobManager, get_export_manager
from app.services.instance_archive.models import ArchivePaths
from app.services.instance_archive.policy import is_standard_layout

logger = logging.getLogger(__name__)

ALERT_COMPONENT = "instance_backup"


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class AutoBackupView:
    settings: AutoBackupSettings
    state: AutoBackupState
    directory: Path
    reachable: bool
    due: bool
    overdue: bool
    running: bool
    backups: tuple[BackupFile, ...]
    last: BackupFile | None


class AutoBackupService:
    def __init__(
        self,
        *,
        paths: ArchivePaths,
        manager: ExportJobManager,
        app_version: str,
        deploy_mode: str,
        publish_alert: Callable[[str], None],
        clock: Callable[[], datetime] = _utc_now,
        folder_guard: FolderGuard | None = None,
        transfer_guard: FolderGuard | None = None,
    ) -> None:
        self._paths = paths
        self._manager = manager
        self._store = AutoBackupStore(paths)
        self._clock = clock
        self._folder = folder_guard or FolderGuard()
        self._publish_alert = publish_alert
        self._loop: asyncio.AbstractEventLoop | None = None
        self._active = threading.Event()  # from the moment a background run is requested until it has finished
        self._runner = AutoBackupRunner(
            paths=paths,
            store=self._store,
            manager=manager,
            folder_guard=self._folder,
            transfer_guard=transfer_guard or FolderGuard(TRANSFER_STALL_SECONDS),
            app_version=app_version,
            deploy_mode=deploy_mode,
            notify_failure=self._alert_from_worker,
            clock=clock,
        )

    def view(self) -> AutoBackupView:
        """What is backed up is read from the folder, not remembered: the files there are the only truth.
        A folder that cannot be read, or does not answer, is unknown, never taken for empty."""
        settings, state = self._store.load()
        directory = destination_path(self._paths, settings.directory)
        now = self._clock()
        tag = self._store.tag()
        try:
            backups = self._folder.call(lambda: tuple(list_backups(directory, tag)))
            reachable = True
        except OSError:
            backups, reachable = (), False
        last = last_backup(backups, now)
        reference = reference_moment(last.created_at if last else None, reachable, state, now)
        return AutoBackupView(
            settings=settings,
            state=state,
            directory=directory,
            reachable=reachable,
            due=is_due(settings, state, reference, now),
            overdue=is_overdue(settings, state, reference, now),
            running=self._active.is_set(),
            backups=backups,
            last=last,
        )

    async def get_view(self) -> AutoBackupView:
        return await asyncio.to_thread(self.view)

    async def apply(self, settings: AutoBackupSettings) -> AutoBackupView:
        """Save the user's choice, then back up right away if one is due. Turning it on, or pointing it at a folder
        without a recent backup of this instance, is due at once, which also proves the folder works."""
        await asyncio.to_thread(self._save, settings)
        if settings.enabled:
            await self.tick()
        return await self.get_view()

    async def start_run(self) -> None:
        """Back up now, in the background. Raises ``AutoBackupError`` for an unusable folder, ``ExportBusyError`` if busy."""
        await asyncio.to_thread(self._check_can_run)
        if not self._spawn():
            raise ExportBusyError("An export is already running")

    async def tick(self) -> bool:
        """Start a backup when one is due and nothing else is exporting."""
        if not await asyncio.to_thread(self._due_and_idle):
            return False
        return self._spawn()

    def _save(self, settings: AutoBackupSettings) -> None:
        previous, state = self._store.load()
        if settings.enabled:
            prepare_destination_guarded(self._folder, self._paths, settings.directory)
        self._store.save_settings(settings)
        relocated = destination_path(self._paths, settings.directory) != destination_path(self._paths, previous.directory)
        if settings.enabled and (relocated or not previous.enabled) and state.consecutive_failures:
            # A fresh start (turned on again, or another folder): do not make the user wait out a back-off earned before.
            self._store.save_state(AutoBackupState())

    def _check_can_run(self) -> None:
        settings, _ = self._store.load()
        prepare_destination_guarded(self._folder, self._paths, settings.directory)
        if self._active.is_set() or self._manager.is_busy:
            raise ExportBusyError("An export is already running")

    def _due_and_idle(self) -> bool:
        if self._active.is_set() or self._manager.is_busy:
            return False
        return self.view().due

    def _spawn(self) -> bool:
        """Start the background run unless one is under way. Checking and claiming ``_active`` happen on the event
        loop with no ``await`` between them, so two callers that both passed their own checks cannot both start."""
        if self._active.is_set():
            return False
        self._loop = asyncio.get_running_loop()
        self._active.set()
        try:
            threading.Thread(target=self._run_in_background, name="instance-auto-backup", daemon=True).start()
        except BaseException:
            self._active.clear()
            raise
        return True

    def _run_in_background(self) -> None:
        try:
            self._runner.run()
        except ExportBusyError:
            logger.info("[AutoBackup] Skipped: another export is running")
        except Exception:  # worker-thread boundary: the next tick decides again from the recorded state
            logger.exception("[AutoBackup] Backup run crashed")
        finally:
            self._active.clear()

    def _alert_from_worker(self, code: str) -> None:
        loop = self._loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(self._publish_alert, code)


def publish_failure_alert(code: str) -> None:
    """Tell the UI, IM channels and push that scheduled backups keep failing."""
    try:
        get_event_bus().publish(
            AppEvent(
                event_type=AppEventType.HEALTH_ALERT,
                data={
                    "component": ALERT_COMPONENT,
                    "status": "fail",
                    "code": code,
                    "message": "Automatic backup has failed repeatedly and your data may not be protected.",
                    "fix_suggestion": "Open Settings > Backup and restore to check the backup folder and free space.",
                    "layer": "system",
                },
            )
        )
    except Exception:  # an alert must never turn a recorded failure into a crash
        logger.warning("[AutoBackup] Could not publish the failure alert", exc_info=True)


_services: dict[Path, AutoBackupService] = {}
_services_lock = threading.Lock()


def get_auto_backup_service() -> AutoBackupService | None:
    """None in a cloud sandbox or when the main database is not in the standard place."""
    if is_sandbox():
        return None
    settings = get_settings()
    paths = ArchivePaths(Path(settings.database.state_dir))
    if not is_standard_layout(paths.state_dir, Path(settings.database.sqlite_path)):
        return None
    with _services_lock:
        service = _services.get(paths.state_dir)
        if service is None:
            service = AutoBackupService(
                paths=paths,
                manager=get_export_manager(paths),
                app_version=settings.app_version,
                deploy_mode=get_deploy_mode().value,
                publish_alert=publish_failure_alert,
            )
            _services[paths.state_dir] = service
        return service


async def run_auto_backup_tick() -> None:
    """Scheduler job: start a backup if one is due. A failure here must never stop the scheduler."""
    try:
        service = get_auto_backup_service()
        if service is not None:
            await service.tick()
    except Exception:
        logger.exception("[AutoBackup] Scheduler tick failed")
