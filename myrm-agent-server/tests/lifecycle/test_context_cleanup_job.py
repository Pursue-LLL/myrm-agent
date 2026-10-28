"""The daily context cleanup job hands the shared read tracker to the harness cleanup and never skips cleanup.

It also sweeps the cached channel images, and a failing sweep must not stop the rest of the job.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.media.image_enrichment import CHANNEL_IMAGE_RETENTION_DAYS
from app.lifecycle import schedulers


@pytest.fixture(autouse=True)
def _no_spillover_sweep(monkeypatch: pytest.MonkeyPatch) -> None:
    """The workspace spillover sweep is a separate concern and must not touch the real data dir."""
    monkeypatch.setattr("app.services.agent.context_guard_service.ContextGuardService.sweep_all_workspaces", lambda *_: 0)


@pytest.fixture(autouse=True)
def image_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The channel image sweep runs for real, on a temporary directory instead of the real data dir."""
    directory = tmp_path / "channel_images"
    directory.mkdir()
    monkeypatch.setattr("app.channels.media.image_enrichment.channel_image_cache_dir", lambda: directory)
    return directory


@pytest.fixture
def tracker(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    shared = MagicMock()
    monkeypatch.setattr(
        "myrm_agent_harness.runtime.context.file_access_tracker.get_file_access_tracker",
        AsyncMock(return_value=shared),
    )
    return shared


@pytest.fixture
def cleanup(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=3)
    monkeypatch.setattr("myrm_agent_harness.runtime.context.offload.cleanup_orphan_context_files_async", mock)
    return mock


async def test_the_shared_tracker_is_handed_to_the_cleanup(cleanup: AsyncMock, tracker: MagicMock) -> None:
    await schedulers._context_cleanup_job()

    cleanup.assert_awaited_once_with(access_tracker=tracker)


async def test_cleanup_still_runs_by_modification_time_when_the_tracker_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, cleanup: AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(
        "myrm_agent_harness.runtime.context.file_access_tracker.get_file_access_tracker",
        AsyncMock(side_effect=OSError("Read-only file system")),
    )

    with caplog.at_level(logging.WARNING, logger=schedulers.logger.name):
        await schedulers._context_cleanup_job()

    cleanup.assert_awaited_once_with(access_tracker=None)
    assert any("File access tracker unavailable" in record.getMessage() for record in caplog.records)


@pytest.mark.usefixtures("cleanup", "tracker")
async def test_cached_channel_images_past_their_retention_are_swept(image_cache: Path) -> None:
    expired = image_cache / "expired.jpg"
    fresh = image_cache / "fresh.jpg"
    for image, unused_days in ((expired, CHANNEL_IMAGE_RETENTION_DAYS + 1), (fresh, 1)):
        image.write_bytes(b"img")
        stamp = time.time() - unused_days * 86400
        os.utime(image, (stamp, stamp))

    await schedulers._context_cleanup_job()

    assert not expired.exists()
    assert fresh.exists()


@pytest.mark.usefixtures("tracker")
async def test_a_failing_image_sweep_does_not_fail_the_job(
    monkeypatch: pytest.MonkeyPatch, cleanup: AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(
        "app.channels.media.image_enrichment.sweep_channel_image_cache", MagicMock(side_effect=OSError("Input/output error"))
    )

    with caplog.at_level(logging.WARNING, logger=schedulers.logger.name):
        await schedulers._context_cleanup_job()

    cleanup.assert_awaited_once()
    assert any("Channel image cache sweep failed" in record.getMessage() for record in caplog.records)
