"""Background export jobs: lifecycle, single-flight, cleanup."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.services.instance_archive import ArchivePaths, ExportBusyError, ExportJobManager, JobState


def _start(manager: ExportJobManager, **overrides: object):
    kwargs: dict[str, object] = {
        "user_id": "user-a",
        "app_version": "1.0.0",
        "deploy_mode": "local",
        "config_key": None,
        "passphrase": None,
    }
    kwargs.update(overrides)
    return manager.start(**kwargs)  # type: ignore[arg-type]


def _wait(manager: ExportJobManager, job_id: str) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        job = manager.get(job_id)
        assert job is not None
        if job.state is not JobState.RUNNING:
            return
        time.sleep(0.05)
    raise AssertionError("export did not finish")


def test_job_completes_with_progress_and_discard_deletes_the_file(source_state: Path) -> None:
    manager = ExportJobManager(ArchivePaths(source_state))

    job = _start(manager)
    _wait(manager, job.job_id)

    assert job.state is JobState.DONE
    assert job.progress is not None
    assert job.progress.files_done == job.progress.files_total
    path = manager.archive_path(job)
    assert path is not None and path.is_file()
    assert path.parent == ArchivePaths(source_state).exports

    manager.discard(job.job_id)
    assert not path.exists()
    assert manager.get(job.job_id) is None


def test_missing_main_database_fails_the_job_instead_of_shipping_an_empty_archive(tmp_path: Path) -> None:
    state = tmp_path / "empty"
    state.mkdir()
    (state / "note.txt").write_text("x")
    manager = ExportJobManager(ArchivePaths(state))

    job = _start(manager)
    _wait(manager, job.job_id)

    assert job.state is JobState.FAILED
    assert job.error_code == "export_failed"
    assert manager.archive_path(job) is None
    assert not list(ArchivePaths(state).exports.glob("*.zip*"))


def test_only_one_export_runs_at_a_time(source_state: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import threading

    gate = threading.Event()
    from app.services.instance_archive import export_jobs

    real = export_jobs.build_export

    def slow(**kwargs: object):
        gate.wait(10)
        return real(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(export_jobs, "build_export", slow)
    manager = ExportJobManager(ArchivePaths(source_state))
    first = _start(manager)

    with pytest.raises(ExportBusyError):
        _start(manager)

    gate.set()
    _wait(manager, first.job_id)
    assert first.state is JobState.DONE


def test_stale_archives_are_swept_on_the_next_start(source_state: Path) -> None:
    paths = ArchivePaths(source_state)
    paths.exports.mkdir(parents=True)
    stale = paths.exports / "abandoned.zip"
    stale.write_bytes(b"x")
    old = time.time() - 7 * 3600
    import os

    os.utime(stale, (old, old))
    manager = ExportJobManager(paths)

    job = _start(manager)
    _wait(manager, job.job_id)

    assert not stale.exists()
