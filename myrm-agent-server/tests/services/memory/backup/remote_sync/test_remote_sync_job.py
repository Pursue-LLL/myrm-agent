"""Scheduled remote backup tick: when it runs, how every outcome is recorded and when the user is alerted.

[INPUT]
app.services.memory.backup.remote_sync.job::sync_tick/record_manual_success/strategy_from_config/publish_failure_alert
app.services.memory.backup.remote_sync.state::RemoteSyncStore

[OUTPUT]
That a due backup runs with the user's settings, a backup that is not due costs nothing, a failure is retried at the
next tick and reported once, and a busy run is not mistaken for a failure.

[POS]
The real tick and the real state files; only the backup runner (covered by the round-trip tests) and the memory manager
are replaced, so what is asserted is the orchestration.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from myrm_agent_harness.toolkits.memory import MemoryManager

from app.services.event.app_event_bus import AppEvent, AppEventType
from app.services.instance_archive.models import ArchivePaths
from app.services.memory.backup.remote_sync import ALERT_COMPONENT, job
from app.services.memory.backup.remote_sync.job import (
    publish_failure_alert,
    record_manual_success,
    strategy_from_config,
    sync_tick,
)
from app.services.memory.backup.remote_sync.runner import RemoteBackupResult
from app.services.memory.backup.remote_sync.state import RemoteSyncState, RemoteSyncStore
from app.services.memory.backup.remote_sync.storage import RemoteBackupStrategy, S3BackupStrategy, WebDAVBackupStrategy
from tests.support.in_memory_remote_backup import InMemoryBackupStrategy

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)
CONFIG: dict[str, object] = {
    "enabled": True,
    "autoSync": True,
    "provider": "webdav",
    "syncInterval": 1440,
    "maxBackups": 4,
    "deviceName": "laptop",
    "webdav": {"host": "https://dav.example.test", "username": "u", "password": "p"},
}
_OK = RemoteBackupResult(status="ok", file_name="myrm.backup.json.gz")
_FAILED = RemoteBackupResult(status="failed", error_code="upload", error="Remote upload failed after retries")
_BUSY = RemoteBackupResult(status="busy", error="Backup already in progress")


class _Rig:
    """Everything the tick touches, recorded."""

    def __init__(self, store: RemoteSyncStore) -> None:
        self.store = store
        self.outcome = _OK
        self.runs: list[dict[str, object]] = []
        self.managers = 0
        self.alerts: list[str] = []

    async def tick(
        self,
        value: Mapping[str, object] | None = CONFIG,
        *,
        now: datetime = NOW,
        strategy_factory: Callable[[Mapping[str, object]], RemoteBackupStrategy] | None = None,
        manager_factory: Callable[[], Awaitable[MemoryManager]] | None = None,
    ) -> None:
        async def new_manager() -> MemoryManager:
            self.managers += 1
            return MagicMock(spec=MemoryManager)

        await sync_tick(
            value,
            store=self.store,
            manager_factory=manager_factory or new_manager,
            now=now,
            strategy_factory=strategy_factory or (lambda _value: InMemoryBackupStrategy()),
            alert=self.alerts.append,
        )


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Rig:
    rig = _Rig(RemoteSyncStore(ArchivePaths(tmp_path)))

    async def fake_run(
        manager: MemoryManager, strategy: RemoteBackupStrategy, *, instance_tag: str, device_name: str, max_backups: int
    ) -> RemoteBackupResult:
        rig.runs.append({"instance_tag": instance_tag, "device_name": device_name, "max_backups": max_backups})
        return rig.outcome

    monkeypatch.setattr(job, "run_remote_backup", fake_run)
    return rig


@pytest.mark.parametrize(
    "value",
    [None, {}, {**CONFIG, "enabled": False}, {**CONFIG, "autoSync": False}, {**CONFIG, "enabled": "yes"}],
    ids=["unset", "empty", "disabled", "auto-sync-off", "not-a-boolean"],
)
async def test_nothing_runs_while_the_sync_is_off(rig: _Rig, value: Mapping[str, object] | None) -> None:
    await rig.tick(value)

    assert rig.runs == []
    assert rig.managers == 0
    assert rig.store.load() == RemoteSyncState()


async def test_a_due_backup_runs_with_the_users_settings_and_the_success_is_recorded(rig: _Rig) -> None:
    await rig.tick()

    assert rig.runs == [{"instance_tag": rig.store.tag(), "device_name": "laptop", "max_backups": 4}]
    assert rig.store.load() == RemoteSyncState(last_success_at=NOW, last_attempt_at=NOW)


async def test_a_backup_that_is_not_due_does_not_even_build_a_memory_manager(rig: _Rig) -> None:
    rig.store.save(RemoteSyncState(last_success_at=NOW - timedelta(hours=1), last_attempt_at=NOW - timedelta(hours=1)))

    await rig.tick()

    assert (rig.runs, rig.managers) == ([], 0)


@pytest.mark.parametrize(("hours_since_success", "runs"), [(5, 0), (7, 1)])
async def test_the_interval_the_user_chose_decides_not_a_fixed_one(rig: _Rig, hours_since_success: int, runs: int) -> None:
    rig.store.save(RemoteSyncState(last_success_at=NOW - timedelta(hours=hours_since_success)))

    await rig.tick({**CONFIG, "syncInterval": 360})

    assert len(rig.runs) == runs


async def test_the_state_survives_a_restart_so_a_restart_does_not_upload_again(tmp_path: Path, rig: _Rig) -> None:
    await rig.tick()
    assert len(rig.runs) == 1

    restarted = _Rig(RemoteSyncStore(ArchivePaths(tmp_path)))
    restarted.outcome = rig.outcome
    await restarted.tick(now=NOW + timedelta(minutes=5))

    assert restarted.runs == []


async def test_a_failed_backup_is_recorded_and_retried_at_the_next_tick(rig: _Rig) -> None:
    rig.outcome = _FAILED

    await rig.tick()
    first = rig.store.load()
    await rig.tick(now=NOW + HOUR)
    second = rig.store.load()

    assert len(rig.runs) == 2
    assert (first.consecutive_failures, first.last_error_code, first.last_success_at) == (1, "upload", None)
    assert (second.consecutive_failures, second.last_attempt_at) == (2, NOW + HOUR)


async def test_repeated_failures_alert_once_per_failure_streak(rig: _Rig) -> None:
    rig.outcome = _FAILED

    for hours in range(5):
        await rig.tick(now=NOW + hours * HOUR)

    assert rig.alerts == ["upload"]
    assert rig.store.load().alerted is True


async def test_a_success_ends_the_streak_and_a_later_streak_can_alert_again(rig: _Rig) -> None:
    rig.outcome = _FAILED
    for hours in range(3):
        await rig.tick(now=NOW + hours * HOUR)
    rig.outcome = _OK
    await rig.tick(now=NOW + 3 * HOUR)
    assert rig.store.load() == RemoteSyncState(last_success_at=NOW + 3 * HOUR, last_attempt_at=NOW + 3 * HOUR)

    rig.outcome = _FAILED
    later = NOW + timedelta(days=4)
    for hours in range(3):
        await rig.tick(now=later + hours * HOUR)

    assert rig.alerts == ["upload", "upload"]


async def test_a_short_outage_after_a_recent_success_stays_quiet(rig: _Rig) -> None:
    rig.store.save(RemoteSyncState(last_success_at=NOW - timedelta(hours=25)))
    rig.outcome = _FAILED

    for hours in range(3):
        await rig.tick(now=NOW + hours * HOUR)

    assert rig.store.load().consecutive_failures == 3
    assert rig.alerts == []


async def test_a_backup_already_running_is_not_recorded_as_a_failure(rig: _Rig) -> None:
    rig.outcome = _BUSY

    await rig.tick()
    await rig.tick(now=NOW + HOUR)

    assert rig.store.load() == RemoteSyncState()
    assert rig.alerts == []


async def test_a_provider_that_cannot_be_built_is_recorded_as_a_settings_failure(rig: _Rig) -> None:
    def refuse(_value: Mapping[str, object]) -> RemoteBackupStrategy:
        raise ValueError("Unknown backup provider: ftp")

    await rig.tick({**CONFIG, "provider": "ftp"}, strategy_factory=refuse)

    state = rig.store.load()
    assert (state.consecutive_failures, state.last_error_code) == (1, "config")
    assert (rig.runs, rig.managers) == ([], 0)


async def test_a_memory_manager_that_cannot_be_created_is_recorded_as_an_internal_failure(rig: _Rig) -> None:
    async def broken() -> MemoryManager:
        raise RuntimeError("no embedding model")

    await rig.tick(manager_factory=broken)

    state = rig.store.load()
    assert (state.consecutive_failures, state.last_error_code) == (1, "internal")
    assert rig.runs == []


async def test_a_manual_backup_ends_the_streak_so_the_next_tick_does_not_repeat_it(rig: _Rig) -> None:
    rig.store.save(
        RemoteSyncState(last_success_at=NOW - timedelta(days=3), consecutive_failures=3, last_error_code="upload", alerted=True)
    )

    record_manual_success(rig.store, NOW)
    await rig.tick(now=NOW + HOUR)

    assert rig.store.load() == RemoteSyncState(last_success_at=NOW, last_attempt_at=NOW)
    assert rig.runs == []


def test_a_webdav_provider_builds_a_webdav_strategy() -> None:
    assert isinstance(strategy_from_config(CONFIG), WebDAVBackupStrategy)


def test_an_s3_provider_builds_an_s3_strategy_with_path_style_addressing_by_default() -> None:
    strategy = strategy_from_config(
        {
            "provider": "s3",
            "s3": {"endpoint": "https://s3.example.test", "bucket": "vault", "accessKeyId": "id", "secretAccessKey": "secret"},
        }
    )

    assert isinstance(strategy, S3BackupStrategy)
    assert strategy._config.force_path_style is True
    assert strategy._config.prefix == "myrm-backups/"


@pytest.mark.parametrize("value", [{}, {"provider": ""}, {"provider": "ftp"}, {"provider": 3}])
def test_a_missing_or_unknown_provider_is_rejected(value: Mapping[str, object]) -> None:
    with pytest.raises(ValueError, match="provider"):
        strategy_from_config(value)


def test_the_alert_goes_to_the_event_bus_as_a_health_alert_for_this_feature(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[AppEvent] = []
    monkeypatch.setattr(job, "get_event_bus", lambda: SimpleNamespace(publish=events.append))

    publish_failure_alert("upload")

    assert [event.event_type for event in events] == [AppEventType.HEALTH_ALERT]
    assert events[0].data["component"] == ALERT_COMPONENT == "remote_memory_backup"
    assert (events[0].data["status"], events[0].data["code"]) == ("fail", "upload")


def test_an_alert_that_cannot_be_published_never_turns_a_recorded_failure_into_a_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_bus() -> object:
        raise RuntimeError("bus down")

    monkeypatch.setattr(job, "get_event_bus", broken_bus)

    publish_failure_alert("upload")
