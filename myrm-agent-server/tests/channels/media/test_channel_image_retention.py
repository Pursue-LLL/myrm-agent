"""Images cached for received messages are kept for the days they may still be cited, and then removed.

``{DATA_DIR}/cache/channel_images/`` gets a file per distinct image and nothing ever removed one. A file's age is its
modification time, so receiving the same image again must restart it, or an image still in use would expire.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from app.channels.media.image_enrichment import (
    CHANNEL_IMAGE_RETENTION_DAYS,
    _save_to_cache,
    sweep_channel_image_cache,
)
from app.channels.types import InboundMessage

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


class TestReuseRestartsTheAge:
    def test_the_same_image_arriving_again_is_not_expired(self, cache_dir: Path) -> None:
        msg = InboundMessage(channel="telegram", sender_id="u1", content="")
        first = _save_to_cache(b"img", "image/jpeg", msg)
        assert first is not None
        path = Path(first)
        stamp = time.time() - (CHANNEL_IMAGE_RETENTION_DAYS + 10) * _DAY_S
        os.utime(path, (stamp, stamp))

        again = _save_to_cache(b"img", "image/jpeg", msg)

        assert again == first
        assert time.time() - path.stat().st_mtime < 60
        assert path.read_bytes() == b"img"
        assert sweep_channel_image_cache() == 0

    def test_a_file_removed_between_arrivals_is_written_again(self, cache_dir: Path) -> None:
        msg = InboundMessage(channel="telegram", sender_id="u1", content="")
        first = _save_to_cache(b"img", "image/jpeg", msg)
        assert first is not None
        Path(first).unlink()

        again = _save_to_cache(b"img", "image/jpeg", msg)

        assert again == first
        assert Path(first).read_bytes() == b"img"


class TestSweep:
    def test_only_images_unused_for_longer_than_the_retention_are_removed(self, cache_dir: Path) -> None:
        expired = _image(cache_dir, "expired.jpg", unused_days=CHANNEL_IMAGE_RETENTION_DAYS + 1)
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

    def test_one_file_that_cannot_be_removed_does_not_stop_the_sweep(
        self, cache_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stuck = _image(cache_dir, "stuck.jpg", unused_days=CHANNEL_IMAGE_RETENTION_DAYS + 1)
        gone = _image(cache_dir, "gone.jpg", unused_days=CHANNEL_IMAGE_RETENTION_DAYS + 1)
        real_unlink = Path.unlink

        def unlink(self: Path, *args: bool) -> None:
            if self.name == "stuck.jpg":
                raise PermissionError("Operation not permitted")
            real_unlink(self, *args)

        monkeypatch.setattr(Path, "unlink", unlink)

        assert sweep_channel_image_cache() == 1
        assert stuck.exists()
        assert not gone.exists()
