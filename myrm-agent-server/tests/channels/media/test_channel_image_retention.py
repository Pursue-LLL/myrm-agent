"""Images cached for received messages are kept for the days they may still be cited, and then removed.

A file's age is its modification time, so receiving the same image again must restart it, or an image still in use
would expire. A cache that cannot be written or cleaned must never fail the message or the daily cleanup.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

import pytest

from app.channels.media.image_enrichment import (
    CHANNEL_IMAGE_RETENTION_DAYS,
    _save_to_cache,
    logger,
    sweep_channel_image_cache,
    sweep_channel_image_cache_at_startup,
)

_DAY_S = 86400.0


@pytest.fixture
def cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "channel_images"
    directory.mkdir()
    monkeypatch.setattr("app.channels.media.image_enrichment.channel_image_cache_dir", lambda: directory)
    return directory


def _image(directory: Path, name: str, *, unused_days: float) -> Path:
    path = directory / name
    path.write_bytes(b"img")
    stamp = time.time() - unused_days * _DAY_S
    os.utime(path, (stamp, stamp))
    return path


def _expired(directory: Path, name: str) -> Path:
    return _image(directory, name, unused_days=CHANNEL_IMAGE_RETENTION_DAYS + 1)


class TestSaving:
    def test_the_same_image_arriving_again_is_not_expired(self, cache_dir: Path) -> None:
        first = _save_to_cache(b"img", "image/jpeg")
        assert first is not None
        path = Path(first)
        stamp = time.time() - (CHANNEL_IMAGE_RETENTION_DAYS + 10) * _DAY_S
        os.utime(path, (stamp, stamp))

        again = _save_to_cache(b"img", "image/jpeg")

        assert again == first
        assert time.time() - path.stat().st_mtime < 60
        assert path.read_bytes() == b"img"
        assert sweep_channel_image_cache() == 0

    def test_a_file_removed_between_arrivals_is_written_again(self, cache_dir: Path) -> None:
        first = _save_to_cache(b"img", "image/jpeg")
        assert first is not None
        Path(first).unlink()

        again = _save_to_cache(b"img", "image/jpeg")

        assert again == first
        assert Path(first).read_bytes() == b"img"

    def test_a_cache_that_cannot_be_resolved_is_no_cache_rather_than_an_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def unresolvable() -> Path:
            raise OSError("Read-only file system")

        monkeypatch.setattr("app.channels.media.image_enrichment.channel_image_cache_dir", unresolvable)

        assert _save_to_cache(b"img", "image/jpeg") is None


class TestSweep:
    def test_only_images_unused_for_longer_than_the_retention_are_removed(self, cache_dir: Path) -> None:
        expired = _expired(cache_dir, "expired.jpg")
        kept = _image(cache_dir, "kept.jpg", unused_days=CHANNEL_IMAGE_RETENTION_DAYS - 1)

        removed = sweep_channel_image_cache()

        assert removed == 1
        assert not expired.exists()
        assert kept.exists()

    def test_a_cache_directory_that_does_not_exist_yet_is_nothing_to_sweep(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("app.channels.media.image_enrichment.channel_image_cache_dir", lambda: tmp_path / "absent")

        assert sweep_channel_image_cache() == 0

    def test_a_subdirectory_is_left_alone(self, cache_dir: Path) -> None:
        nested = cache_dir / "nested"
        nested.mkdir()
        stamp = time.time() - (CHANNEL_IMAGE_RETENTION_DAYS + 5) * _DAY_S
        os.utime(nested, (stamp, stamp))

        assert sweep_channel_image_cache() == 0
        assert nested.is_dir()

    def test_files_that_cannot_be_removed_are_left_and_reported_once(
        self, cache_dir: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        stuck = [_expired(cache_dir, f"stuck{n}.jpg") for n in range(3)]
        gone = _expired(cache_dir, "gone.jpg")
        real_unlink = Path.unlink

        def unlink(self: Path, *args: bool) -> None:
            if self.name.startswith("stuck"):
                raise PermissionError("Operation not permitted")
            real_unlink(self, *args)

        monkeypatch.setattr(Path, "unlink", unlink)

        with caplog.at_level(logging.WARNING, logger=logger.name):
            removed = sweep_channel_image_cache()

        assert removed == 1
        assert not gone.exists()
        assert all(path.exists() for path in stuck)
        warnings = [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "Failed to remove 3 expired channel images" in warnings[0]

    def test_a_file_removed_by_someone_else_during_the_sweep_is_not_a_failure(
        self, cache_dir: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        vanished = _expired(cache_dir, "vanished.jpg")
        real_unlink = Path.unlink

        def unlink(self: Path, *args: bool) -> None:
            real_unlink(self, *args)
            raise FileNotFoundError(self.name)

        monkeypatch.setattr(Path, "unlink", unlink)

        with caplog.at_level(logging.WARNING, logger=logger.name):
            removed = sweep_channel_image_cache()

        assert removed == 0
        assert not vanished.exists()
        assert not caplog.records


class TestStartupSweep:
    """The daily job runs at 03:00 only while the server is up; a machine that is off then still gets its sweep."""

    async def test_expired_images_are_removed_and_recent_ones_kept(self, cache_dir: Path) -> None:
        expired = _expired(cache_dir, "expired.jpg")
        kept = _image(cache_dir, "kept.jpg", unused_days=CHANNEL_IMAGE_RETENTION_DAYS - 1)

        await sweep_channel_image_cache_at_startup()

        assert not expired.exists()
        assert kept.exists()

    async def test_the_removal_is_reported_only_when_something_was_removed(
        self, cache_dir: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=logger.name):
            await sweep_channel_image_cache_at_startup()
            assert not caplog.records

            _expired(cache_dir, "expired.jpg")
            await sweep_channel_image_cache_at_startup()

        [record] = caplog.records
        assert "removed 1 expired channel images" in record.getMessage()

    async def test_the_sweep_does_not_run_on_the_event_loop_thread(
        self, cache_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ran_on: list[int] = []

        def record_thread() -> int:
            ran_on.append(threading.get_ident())
            return 0

        monkeypatch.setattr("app.channels.media.image_enrichment.sweep_channel_image_cache", record_thread)

        await sweep_channel_image_cache_at_startup()

        assert ran_on
        assert ran_on != [threading.get_ident()]
