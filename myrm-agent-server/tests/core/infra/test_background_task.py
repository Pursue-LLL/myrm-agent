"""Unit tests for app.core.infra.background_task.spawn_observed_task."""

from __future__ import annotations

import asyncio
import logging

import pytest

from app.core.infra.background_task import spawn_observed_task

_LOGGER_NAME = "app.core.infra.background_task"


class _CaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def captured() -> _CaptureHandler:
    handler = _CaptureHandler()
    logging.getLogger(_LOGGER_NAME).addHandler(handler)
    yield handler
    logging.getLogger(_LOGGER_NAME).removeHandler(handler)


async def _crash() -> None:
    raise RuntimeError("boom during scheduler startup")


async def _never_finishes() -> None:
    await asyncio.Event().wait()


async def test_a_crashed_task_is_reported_as_an_error(captured: _CaptureHandler) -> None:
    task = spawn_observed_task(_crash(), name="db_maintenance")

    await asyncio.wait({task})

    errors = [record for record in captured.records if record.levelno == logging.ERROR]
    assert len(errors) == 1
    assert errors[0].getMessage() == "[db_maintenance] background task exited: boom during scheduler startup"
    # The callback read the exception, so nothing is left to leak at task collection.
    assert task.exception() is not None


async def test_the_exception_does_not_stay_unretrieved(captured: _CaptureHandler) -> None:
    """A bare create_task would leave the failure unread; the observed spawn retrieves it."""
    task = spawn_observed_task(_crash(), name="context_cleanup")

    await asyncio.wait({task})

    assert task.done()
    assert isinstance(task.exception(), RuntimeError)


async def test_cancellation_is_the_normal_shutdown_path_and_is_not_reported(captured: _CaptureHandler) -> None:
    task = spawn_observed_task(_never_finishes(), name="approval_ttl_cleanup")
    await asyncio.sleep(0)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert task.cancelled()
    assert captured.records == []


async def test_a_healthy_task_logs_nothing(captured: _CaptureHandler) -> None:
    async def _finish() -> None:
        return None

    task = spawn_observed_task(_finish(), name="login_session_cleanup")
    await asyncio.wait({task})

    assert captured.records == []
