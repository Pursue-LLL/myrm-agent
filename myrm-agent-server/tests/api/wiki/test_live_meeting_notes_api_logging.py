"""A failed live meeting request is logged with its traceback, even when the exception has no message.

A timeout carries no message, so the traceback is the only thing in the log that says what went wrong.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.services.meeting_notes.live_notes import LiveNotesSession
from tests.support.live_meeting_api import build_client, double, ingest_all
from tests.support.wiki_clip_client import bypass_loopback_auth

_ROUTE_LOGGER = "app.api.wiki.routes.meeting"


@pytest.fixture(autouse=True)
def _bypass_auth() -> Iterator[None]:
    with bypass_loopback_auth():
        yield


def _route_logs(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == _ROUTE_LOGGER]


def test_finalize_failure_is_logged_with_its_traceback_even_without_an_error_message(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A timeout carries no message, so only the traceback says what went wrong."""
    client, archiver, _structure = build_client(tmp_path)
    ingest_all(client, "silent-timeout")
    double(archiver._llm).ainvoke.side_effect = TimeoutError()

    with caplog.at_level(logging.ERROR, logger=_ROUTE_LOGGER):
        response = client.post("/api/v1/wiki/meeting-notes/live/silent-timeout/finalize?auto_compile=false")

    assert response.status_code == 500
    [record] = _route_logs(caplog)
    assert record.levelno == logging.ERROR
    assert record.exc_info is not None
    assert record.exc_info[0] is TimeoutError


def test_ingest_failure_is_logged_with_its_traceback_even_without_an_error_message(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _archiver, _structure = build_client(tmp_path)

    def _times_out(*_args: object, **_kwargs: object) -> bool:
        raise TimeoutError

    monkeypatch.setattr(LiveNotesSession, "ingest", _times_out)

    with caplog.at_level(logging.ERROR, logger=_ROUTE_LOGGER):
        response = client.post("/api/v1/wiki/meeting-notes/live/silent-timeout/ingest", json={"text": "hello", "line_id": "l1"})

    assert response.status_code == 500
    [record] = _route_logs(caplog)
    assert record.levelno == logging.ERROR
    assert record.exc_info is not None
    assert record.exc_info[0] is TimeoutError
