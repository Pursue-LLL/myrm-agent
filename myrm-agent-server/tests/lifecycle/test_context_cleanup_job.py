"""The daily context cleanup job hands the shared read tracker to the harness cleanup and never skips cleanup."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.lifecycle import schedulers


@pytest.fixture(autouse=True)
def _no_spillover_sweep(monkeypatch: pytest.MonkeyPatch) -> None:
    """The workspace spillover sweep is a separate concern and must not touch the real data dir."""
    monkeypatch.setattr("app.services.agent.context_guard_service.ContextGuardService.sweep_all_workspaces", lambda *_: 0)


@pytest.fixture
def cleanup(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=3)
    monkeypatch.setattr("myrm_agent_harness.runtime.context.offload.cleanup_orphan_context_files_async", mock)
    return mock


async def test_the_shared_tracker_is_handed_to_the_cleanup(monkeypatch: pytest.MonkeyPatch, cleanup: AsyncMock) -> None:
    tracker = MagicMock()
    monkeypatch.setattr(
        "myrm_agent_harness.runtime.context.file_access_tracker.get_file_access_tracker",
        AsyncMock(return_value=tracker),
    )

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
