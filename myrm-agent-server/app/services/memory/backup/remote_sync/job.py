"""One tick of the scheduled remote memory backup, and the wiring a backup cycle needs.

[INPUT]
- app.services.memory.backup.remote_sync.runner::run_remote_backup, RemoteBackupResult (POS: one backup cycle, outcome as a value)
- app.services.memory.backup.remote_sync.storage::WebDAVBackupStrategy, S3BackupStrategy and their configs (POS: remote storage)
- app.services.memory.backup.remote_sync.schedule::interval_minutes, is_due, should_alert (POS: pure schedule rules)
- app.services.memory.backup.remote_sync.state::RemoteSyncStore (POS: persisted outcome of the scheduled runs)
- app.services.event.app_event_bus::get_event_bus (POS: HEALTH_ALERT fan-out to the UI, IM and push)

[OUTPUT]
- sync_tick: runs the backup when it is enabled and due, records every outcome, alerts once per failure streak
- record_manual_success: a backup the user started ends a failure streak
- strategy_from_config: the stored ``backupSync`` settings as a WebDAV or S3 strategy
- publish_failure_alert / ALERT_COMPONENT: the HEALTH_ALERT that tells the user the backups keep failing

[POS]
Settings, clock, memory manager, storage and alert are all handed in, so the orchestration is exercised without a
scheduler. A tick never raises into the scheduler for a backup problem: a settings error, a memory store that cannot be
opened and a failed cycle are recorded as failures (retried at the next tick), a cycle that finds another one running
is neither a success nor a failure. The alert goes out on the event loop that runs the tick, once per failure streak.
Manual backups never start a streak: the user is looking at the result.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime
from typing import TYPE_CHECKING

from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus
from app.services.memory.backup.remote_sync.runner import run_remote_backup
from app.services.memory.backup.remote_sync.schedule import interval_minutes, is_due, should_alert
from app.services.memory.backup.remote_sync.state import RemoteSyncStore
from app.services.memory.backup.remote_sync.storage import (
    RemoteBackupStrategy,
    S3BackupConfig,
    S3BackupStrategy,
    WebDAVBackupConfig,
    WebDAVBackupStrategy,
)

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory import MemoryManager

logger = logging.getLogger(__name__)

ALERT_COMPONENT = "remote_memory_backup"

_DEFAULT_MAX_BACKUPS = 10


def strategy_from_config(value: Mapping[str, object]) -> RemoteBackupStrategy:
    """The stored ``backupSync`` settings as a storage strategy; raises ``ValueError`` for a provider it does not know."""
    provider = value.get("provider")
    if provider == "webdav":
        webdav = _section(value, "webdav")
        return WebDAVBackupStrategy(
            WebDAVBackupConfig(
                host=_text(webdav, "host"),
                username=_text(webdav, "username"),
                password=_text(webdav, "password"),
                path=_text(webdav, "path", "/myrm-backups"),
            )
        )
    if provider == "s3":
        s3 = _section(value, "s3")
        return S3BackupStrategy(
            S3BackupConfig(
                endpoint=_text(s3, "endpoint"),
                region=_text(s3, "region"),
                bucket=_text(s3, "bucket"),
                access_key_id=_text(s3, "accessKeyId"),
                secret_access_key=_text(s3, "secretAccessKey"),
                prefix=_text(s3, "prefix", "myrm-backups/"),
                force_path_style=_flag(s3, "forcePathStyle", True),
            )
        )
    raise ValueError(f"Unsupported or missing backup provider: {provider!r}")


def publish_failure_alert(code: str) -> None:
    """Tell the UI, IM channels and push that scheduled remote backups keep failing."""
    try:
        get_event_bus().publish(
            AppEvent(
                event_type=AppEventType.HEALTH_ALERT,
                data={
                    "component": ALERT_COMPONENT,
                    "status": "fail",
                    "code": code,
                    "message": "Automatic cloud sync of your memories has failed repeatedly and they may not be protected off this device.",
                    "fix_suggestion": "Open Memory > Cloud Sync to check the connection and run a backup manually.",
                    "layer": "system",
                },
            )
        )
    except Exception:  # an alert must never turn a recorded failure into a crash
        logger.warning("Could not publish the remote memory backup failure alert", exc_info=True)


async def sync_tick(
    value: Mapping[str, object] | None,
    *,
    store: RemoteSyncStore,
    manager_factory: Callable[[], Awaitable[MemoryManager]],
    now: datetime,
    strategy_factory: Callable[[Mapping[str, object]], RemoteBackupStrategy] = strategy_from_config,
    alert: Callable[[str], None] = publish_failure_alert,
) -> None:
    """Run a backup when ``value`` (the stored ``backupSync`` settings) enables the sync and the interval has passed."""
    if value is None or value.get("enabled") is not True or value.get("autoSync") is not True:
        return
    interval = interval_minutes(value.get("syncInterval"))
    if not is_due(store.load(), interval, now):
        return

    try:
        strategy = strategy_factory(value)
    except ValueError as exc:
        logger.warning("Scheduled remote memory backup is not configured correctly: %s", exc)
        _record_failure(store, "config", now, interval, alert)
        return

    try:
        manager = await manager_factory()
        result = await run_remote_backup(
            manager,
            strategy,
            instance_tag=store.tag(),
            device_name=_text(value, "deviceName"),
            max_backups=_count(value, "maxBackups", _DEFAULT_MAX_BACKUPS),
        )
    except Exception:
        logger.exception("Scheduled remote memory backup could not start")
        _record_failure(store, "internal", now, interval, alert)
        return

    if result.status == "busy":
        logger.info("Scheduled remote memory backup skipped: another backup is running")
    elif result.status == "ok":
        store.save(store.load().succeeded(now))
        logger.info("Scheduled remote memory backup completed: %s", result.file_name)
    else:
        logger.warning("Scheduled remote memory backup failed (%s): %s", result.error_code, result.error)
        _record_failure(store, result.error_code or "internal", now, interval, alert)


def record_manual_success(store: RemoteSyncStore, now: datetime) -> None:
    """A backup the user ran by hand proves the remote works now: the failure streak ends and the schedule restarts."""
    store.save(store.load().succeeded(now))


def _record_failure(store: RemoteSyncStore, code: str, now: datetime, interval: int, alert: Callable[[str], None]) -> None:
    # Read the state again: the cycle that just ended may have taken minutes, and a manual backup can have recorded in between.
    state = store.load().failed(code, now)
    if should_alert(state, interval, now):
        alert(code)
        state = state.mark_alerted()
    store.save(state)


def _section(config: Mapping[str, object], key: str) -> Mapping[str, object]:
    section = config.get(key)
    return section if isinstance(section, Mapping) else {}


def _text(config: Mapping[str, object], key: str, default: str = "") -> str:
    value = config.get(key)
    return value if isinstance(value, str) else default


def _flag(config: Mapping[str, object], key: str, default: bool) -> bool:
    value = config.get(key)
    return value if isinstance(value, bool) else default


def _count(config: Mapping[str, object], key: str, default: int) -> int:
    value = config.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else default
