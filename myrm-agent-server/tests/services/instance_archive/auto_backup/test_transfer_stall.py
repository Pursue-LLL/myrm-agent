"""A backup folder that stops answering mid-copy ends the run as a recorded failure instead of leaving it running forever."""

from __future__ import annotations

import os
import shutil
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.instance_archive.auto_backup import runner as runner_module
from app.services.instance_archive.auto_backup.folder_guard import FolderGuard
from app.services.instance_archive.auto_backup.models import AutoBackupState
from tests.services.instance_archive.auto_backup.harness import ON, Harness, scheduled_run_ends
from tests.services.instance_archive.auto_backup.rig import Rig, build_rig

STALL = 0.6
COPY_BUFFER = 512  # bytes read and written at a time, so a piece is two writes
SYNC_EVERY = 1024  # bytes written between two syncs of the destination, in the tests that look at them
FAILURE_CODE = "backup_write_failed"  # its copy asks the user to check that the folder is available
WORKER = "auto-backup-folder"


class Hung:
    """Calls that block until released, as the ones on a hard-mounted share whose server stopped answering do."""

    def __init__(self) -> None:
        self.release = threading.Event()
        self.entered = threading.Event()
        self.copies = 0
        self.syncs = 0

    def copy(self, source: object, target: object, length: int = 0) -> None:
        self.copies += 1
        self.entered.set()
        self.release.wait()

    def replace(self, source: str | Path, target: str | Path) -> None:
        """A rename that was under way when the share stopped answering, and completes once it does."""
        held = Path(source).read_bytes()
        self.entered.set()
        self.release.wait()
        Path(target).write_bytes(held)

    def fsync(self, descriptor: int) -> None:
        """The first sync is the export archive's, on the local disk; the next one is the copy's own, into the share."""
        self.syncs += 1
        if self.syncs == 1:
            os.fsync(descriptor)
            return
        self.entered.set()
        self.release.wait()

    def same_volume(self, *_: object) -> bool:
        self.entered.set()
        self.release.wait()
        return True

    def prune(self, *args: object, **kwargs: object) -> list[str]:
        self.entered.set()
        self.release.wait()
        return []


class SlowShare:
    """A healthy share that holds written data back until it is asked to flush it, and takes time to do so."""

    def __init__(self, seconds_per_byte: float) -> None:
        self.seconds_per_byte = seconds_per_byte
        self.flushed = 0
        self.slept = 0.0
        self.syncs = 0

    def fsync(self, descriptor: int) -> None:
        """The first sync is the export archive's, on the local disk; the next ones are the copy's own, into the share."""
        self.syncs += 1
        if self.syncs > 1:
            held = os.fstat(descriptor).st_size - self.flushed
            pause = held * self.seconds_per_byte
            time.sleep(pause)
            self.slept += pause
            self.flushed += held
        os.fsync(descriptor)


def _workers() -> int:
    return sum(1 for thread in threading.enumerate() if thread.name == WORKER)


def _wait_until(condition: Callable[[], bool], seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture(autouse=True)
def _no_worker_left_over() -> None:
    assert _wait_until(lambda: _workers() == 0)


@pytest.fixture
def hung() -> Iterator[Hung]:
    share = Hung()
    yield share
    share.release.set()  # a test never leaves a thread blocked behind it
    _wait_until(lambda: _workers() == 0)


@pytest.fixture
def rig(source_state: Path) -> Rig:
    return build_rig(source_state, transfer_guard=FolderGuard(STALL))


@pytest.fixture
def across_volumes(monkeypatch: pytest.MonkeyPatch) -> None:
    """The backup folder is on another volume, so the archive is copied rather than renamed."""
    monkeypatch.setattr(runner_module, "_same_volume", lambda *_: False)


def _copy_with(monkeypatch: pytest.MonkeyPatch, copy: Callable[..., None]) -> None:
    monkeypatch.setattr(runner_module, "shutil", SimpleNamespace(copyfileobj=copy))


def _copy_in_pieces(monkeypatch: pytest.MonkeyPatch, fsync: Callable[[int], None]) -> None:
    """Sync the destination after every ``SYNC_EVERY`` bytes, through ``fsync`` in place of the real one."""
    monkeypatch.setattr(runner_module, "_COPY_BUFFER", COPY_BUFFER)
    monkeypatch.setattr(runner_module, "_SYNC_EVERY", SYNC_EVERY)
    monkeypatch.setattr(runner_module, "os", SimpleNamespace(replace=os.replace, fsync=fsync))


def _partials(rig: Rig) -> list[Path]:
    return list(rig.default_folder.glob("*.partial"))


@pytest.mark.usefixtures("across_volumes")
def test_a_copy_that_stops_moving_ends_the_run_as_a_recorded_failure(
    rig: Rig, hung: Hung, monkeypatch: pytest.MonkeyPatch
) -> None:
    _copy_with(monkeypatch, hung.copy)

    state = rig.runner.run()

    assert hung.entered.is_set()
    assert (state.consecutive_failures, state.last_error_code) == (1, FAILURE_CODE)
    assert not rig.runner.running
    assert rig.stored() == []


@pytest.mark.usefixtures("across_volumes")
def test_a_copy_that_was_given_up_on_leaves_nothing_behind_when_it_returns_late(
    rig: Rig, hung: Hung, monkeypatch: pytest.MonkeyPatch
) -> None:
    _copy_with(monkeypatch, hung.copy)
    rig.runner.run()

    hung.release.set()

    assert _wait_until(lambda: _workers() == 0)
    assert rig.stored() == []
    assert _partials(rig) == []
    assert not list(rig.paths.exports.glob("*"))


def test_a_publish_that_returns_after_the_run_was_given_up_on_is_taken_back(
    rig: Rig, hung: Hung, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner_module, "os", SimpleNamespace(replace=hung.replace, fsync=os.fsync))

    state = rig.runner.run()
    assert state.last_error_code == FAILURE_CODE
    hung.release.set()

    assert _wait_until(lambda: _workers() == 0)
    assert rig.stored() == []  # a failure was recorded, so no new backup may stay behind
    assert not list(rig.paths.exports.glob("*"))


def _spy_on_publishing(monkeypatch: pytest.MonkeyPatch, hung: Hung) -> list[str]:
    published: list[str] = []

    def replace(source: str | Path, target: str | Path) -> None:
        published.append(str(target))
        os.replace(source, target)

    monkeypatch.setattr(runner_module, "os", SimpleNamespace(replace=replace, fsync=hung.fsync))
    return published


@pytest.mark.usefixtures("across_volumes")
def test_a_copy_stuck_in_its_final_sync_publishes_nothing_when_it_returns_late(
    rig: Rig, hung: Hung, monkeypatch: pytest.MonkeyPatch
) -> None:
    published = _spy_on_publishing(monkeypatch, hung)

    state = rig.runner.run()
    assert state.last_error_code == FAILURE_CODE
    hung.release.set()

    assert _wait_until(lambda: _workers() == 0)
    assert published == []
    assert rig.stored() == [] and _partials(rig) == []


def test_a_rename_that_waited_on_the_share_publishes_nothing_once_the_run_was_given_up_on(
    rig: Rig, hung: Hung, monkeypatch: pytest.MonkeyPatch
) -> None:
    published = _spy_on_publishing(monkeypatch, hung)
    monkeypatch.setattr(runner_module, "_same_volume", hung.same_volume)

    state = rig.runner.run()
    assert state.last_error_code == FAILURE_CODE
    hung.release.set()

    assert _wait_until(lambda: _workers() == 0)
    assert published == []
    assert rig.stored() == []


@pytest.mark.usefixtures("across_volumes")
def test_a_copy_that_is_slow_but_keeps_moving_completes(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    real_copy = shutil.copyfileobj

    def trickle(source, target, length=0):  # noqa: ANN001, ANN202
        for _ in range(4):  # in all longer than the stall window, but never silent for that long
            time.sleep(STALL / 3)
            source.read(0)
        real_copy(source, target, length)

    _copy_with(monkeypatch, trickle)
    started = time.monotonic()

    state = rig.runner.run()

    assert time.monotonic() - started > STALL
    assert state.last_error_code is None
    assert len(rig.stored()) == 1
    assert _partials(rig) == []


@pytest.mark.usefixtures("across_volumes")
def test_a_share_that_is_slow_to_flush_but_takes_every_piece_is_not_given_up_on(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Flushing the whole archive takes longer than the stall window; flushing any one piece of it does not."""
    share = SlowShare(seconds_per_byte=0.25 / SYNC_EVERY)  # a piece takes 0.25 s to flush, the whole 4 KB archive 1.1 s
    _copy_in_pieces(monkeypatch, share.fsync)

    state = rig.runner.run()

    assert state.last_error_code is None
    assert share.slept > STALL
    assert len(rig.stored()) == 1
    assert _partials(rig) == []
    # Once for the export archive, once per full piece, once at the end: a sync per write would stall a real share.
    archive_size = (rig.default_folder / rig.stored()[0]).stat().st_size
    assert share.syncs == 1 + archive_size // SYNC_EVERY + 1


@pytest.mark.usefixtures("across_volumes")
def test_a_share_that_refuses_a_piece_at_its_sync_ends_the_run_as_a_failure_and_leaves_nothing(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    syncs = 0

    def refusing(descriptor: int) -> None:
        nonlocal syncs
        syncs += 1
        if syncs == 2:  # the first sync is the export archive's, on the local disk; the second is the copy's first piece
            raise OSError("no space left on device")
        os.fsync(descriptor)

    _copy_in_pieces(monkeypatch, refusing)

    state = rig.runner.run()

    assert (state.consecutive_failures, state.last_error_code) == (1, FAILURE_CODE)
    assert rig.stored() == []
    assert _partials(rig) == []


def test_a_retention_sweep_that_never_returns_does_not_undo_the_backup(
    source_state: Path, hung: Hung, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = build_rig(source_state, folder_guard=FolderGuard(STALL))
    monkeypatch.setattr(runner_module, "prune", hung.prune)

    state = rig.runner.run()

    assert hung.entered.is_set()
    assert state == AutoBackupState(last_attempt_at=rig.clock.now)
    assert len(rig.stored()) == 1


@pytest.mark.usefixtures("across_volumes")
def test_while_a_copy_is_stuck_the_next_run_fails_and_starts_no_second_copy(
    rig: Rig, hung: Hung, monkeypatch: pytest.MonkeyPatch
) -> None:
    _copy_with(monkeypatch, hung.copy)
    rig.runner.run()

    rig.clock.advance(hours=1)
    state = rig.runner.run()

    assert (state.consecutive_failures, state.last_error_code) == (2, FAILURE_CODE)
    assert hung.copies == 1
    assert _workers() == 1  # the stuck copy's thread, and no other


@pytest.mark.parametrize("copy_dies", [False, True])
def test_a_source_archive_that_cannot_be_removed_does_not_change_the_recorded_outcome(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, copy_dies: bool
) -> None:
    """An abandoned copy may still hold the archive open, which blocks its removal on Windows."""

    def refuse(_: str) -> None:
        raise PermissionError("in use")

    monkeypatch.setattr(rig.manager, "discard", refuse)
    if copy_dies:
        monkeypatch.setattr(runner_module, "_same_volume", lambda *_: False)

        def dying(*_: object, **__: object) -> None:
            raise OSError("device removed")

        _copy_with(monkeypatch, dying)

    state = rig.runner.run()

    assert state.last_error_code == (FAILURE_CODE if copy_dies else None)
    assert len(rig.stored()) == (0 if copy_dies else 1)


@pytest.mark.usefixtures("across_volumes")
async def test_a_stalled_backup_stops_showing_as_running_and_is_recorded_as_a_failure(
    source_state: Path, hung: Hung, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = Harness(source_state, transfer_guard=FolderGuard(STALL))
    harness.service._store.save_settings(ON)
    _copy_with(monkeypatch, hung.copy)

    await scheduled_run_ends(harness)

    view = harness.service.view()
    assert not view.running
    assert (view.state.consecutive_failures, view.state.last_error_code) == (1, FAILURE_CODE)
    assert view.backups == ()
