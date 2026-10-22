"""A backup folder that stops answering is refused or recorded as a failure, and never takes the shared pool with it."""

from __future__ import annotations

import asyncio
import os
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from app.services.instance_archive import ArchivePaths
from app.services.instance_archive.auto_backup import AutoBackupError
from app.services.instance_archive.auto_backup.folder_guard import FolderGuard
from tests.services.instance_archive.auto_backup.harness import ON, Harness, scheduled_run_ends, until

TIMEOUT = 0.3
POOL = min(32, (os.cpu_count() or 1) + 4)  # workers of asyncio's default executor
FAILURE_CODE = "backup_write_failed"  # its copy asks the user to check that the folder is available


class Share:
    """The backup folder is on a hard-mounted share: every access to it blocks until the server answers again.

    The block sits on the filesystem calls themselves, so whichever code touches the folder hangs, however it is reached.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch, folder: Path) -> None:
        self.answers = threading.Event()
        self._folder = folder
        for name in ("resolve", "iterdir"):
            monkeypatch.setattr(Path, name, self._blocking(getattr(Path, name)))

    def _blocking(self, access: Callable[..., object]) -> Callable[..., object]:
        def blocked(path: Path, *args: object, **kwargs: object) -> object:
            if path == self._folder or self._folder in path.parents:
                self.answers.wait()
            return access(path, *args, **kwargs)

        return blocked


@pytest.fixture
def share(monkeypatch: pytest.MonkeyPatch, source_state: Path) -> Iterator[Share]:
    hung = Share(monkeypatch, ArchivePaths(source_state).state_dir / "backups" / "instance")
    yield hung
    hung.answers.set()  # a test never leaves a thread blocked behind it


@pytest.fixture
def guarded(source_state: Path, share: Share) -> Harness:
    return Harness(source_state, folder_guard=FolderGuard(TIMEOUT))


async def test_polling_a_hung_folder_neither_hangs_nor_starves_the_pool_other_features_use(
    guarded: Harness, share: Share
) -> None:
    try:
        # The settings page polls every 2 s while a backup is running; twice the pool's workers is a long stall.
        views = await asyncio.wait_for(
            asyncio.gather(*(guarded.service.get_view() for _ in range(POOL * 2))), timeout=TIMEOUT + 4
        )
        elsewhere = await asyncio.wait_for(asyncio.to_thread(lambda: "free"), timeout=2)
    finally:
        share.answers.set()

    assert all(not view.reachable for view in views)
    assert all(view.backups == () for view in views)
    assert elsewhere == "free"


async def test_saving_settings_while_the_folder_hangs_is_refused_and_keeps_the_previous_ones(
    guarded: Harness, share: Share
) -> None:
    try:
        started = time.monotonic()
        with pytest.raises(AutoBackupError) as refused:
            await asyncio.wait_for(guarded.service.apply(ON), timeout=TIMEOUT + 4)
        waited = time.monotonic() - started
    finally:
        share.answers.set()

    assert refused.value.code == FAILURE_CODE
    assert waited < TIMEOUT + 2
    assert not guarded.service.view().settings.enabled


async def test_backing_up_now_while_the_folder_hangs_is_refused_and_starts_nothing(guarded: Harness, share: Share) -> None:
    try:
        with pytest.raises(AutoBackupError) as refused:
            await asyncio.wait_for(guarded.service.start_run(), timeout=TIMEOUT + 4)
    finally:
        share.answers.set()

    assert refused.value.code == FAILURE_CODE
    assert not guarded.service.view().running


async def test_a_scheduled_backup_that_meets_a_hung_folder_ends_as_a_recorded_failure(guarded: Harness, share: Share) -> None:
    guarded.service._store.save_settings(ON)
    try:
        await scheduled_run_ends(guarded)
    finally:
        share.answers.set()

    state = guarded.service.view().state
    assert (state.consecutive_failures, state.last_error_code) == (1, FAILURE_CODE)
    assert state.last_attempt_at == guarded.clock.now
    assert guarded.alerts == []


async def test_a_hung_folder_alerts_once_when_scheduled_failures_repeat(guarded: Harness, share: Share) -> None:
    guarded.service._store.save_settings(ON)
    main_thread = threading.current_thread().name
    try:
        for expected in (1, 2, 3):
            guarded.clock.advance(hours=2)
            await scheduled_run_ends(guarded)
            assert guarded.service.view().state.consecutive_failures == expected
    finally:
        share.answers.set()

    assert guarded.alerts == [(FAILURE_CODE, main_thread)]


async def test_the_scheduled_backup_succeeds_once_the_share_answers_again(guarded: Harness, share: Share) -> None:
    guarded.service._store.save_settings(ON)
    (guarded.paths.state_dir / "backups" / "instance").mkdir(parents=True)  # the share's folder, from before it went away
    try:
        await scheduled_run_ends(guarded)
    finally:
        share.answers.set()
    await until(lambda: guarded.service.view().reachable, "the folder reading as available again")

    guarded.clock.advance(hours=1)
    assert await guarded.service.tick()
    await guarded.settled()

    view = guarded.service.view()
    assert view.state.consecutive_failures == 0
    assert len(view.backups) == 1


async def test_the_folder_reads_as_available_again_as_soon_as_the_share_answers(guarded: Harness, share: Share) -> None:
    hung = await guarded.service.get_view()
    assert not hung.reachable
    hung.directory.mkdir(parents=True)
    share.answers.set()

    await until(lambda: guarded.service.view().reachable, "the folder reading as available again")
