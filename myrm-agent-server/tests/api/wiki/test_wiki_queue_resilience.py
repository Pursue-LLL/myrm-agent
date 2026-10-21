"""Tests for wiki queue compile resilience API semantics."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.wiki.pipeline.resilience import CompileRunSnapshot

from app.api.wiki.router import _get_wiki_archiver
from tests.support.minimal_app import build_minimal_app


def _stub_queue_publish_mocks(mock_queue: MagicMock) -> None:
    mock_queue.get_stats.return_value = {
        "pending": 0,
        "processing": 0,
        "completed": 0,
        "failed": 0,
    }
    mock_queue.get_compile_run.return_value = CompileRunSnapshot(state="running")


def test_wiki_queue_retry_does_not_resume_worker() -> None:
    mock_queue = MagicMock()
    mock_queue.reset_transient_failed.return_value = 2
    _stub_queue_publish_mocks(mock_queue)
    mock_compiler = MagicMock()
    mock_archiver = MagicMock()
    mock_archiver._queue = mock_queue
    mock_archiver._compiler = mock_compiler

    app = build_minimal_app(preset="wiki")

    async def _override_archiver() -> MagicMock:
        return mock_archiver

    app.dependency_overrides[_get_wiki_archiver] = _override_archiver
    client = TestClient(app)
    try:
        response = client.post("/api/v1/wiki/queue/retry")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["success"] is True
    mock_queue.reset_transient_failed.assert_called_once()
    mock_compiler.resume_compile_worker.assert_not_called()


def test_wiki_queue_retry_all_resumes_worker() -> None:
    mock_queue = MagicMock()
    mock_queue.reset_failed.return_value = 5
    _stub_queue_publish_mocks(mock_queue)
    mock_compiler = MagicMock()
    mock_archiver = MagicMock()
    mock_archiver._queue = mock_queue
    mock_archiver._compiler = mock_compiler

    app = build_minimal_app(preset="wiki")

    async def _override_archiver() -> MagicMock:
        return mock_archiver

    app.dependency_overrides[_get_wiki_archiver] = _override_archiver
    client = TestClient(app)
    try:
        response = client.post("/api/v1/wiki/queue/retry-all")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["success"] is True
    mock_queue.reset_failed.assert_called_once()
    mock_compiler.resume_compile_worker.assert_called_once()
