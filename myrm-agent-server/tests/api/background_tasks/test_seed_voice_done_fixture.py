"""Integration tests for the seed-voice-done local fixture endpoint.

The fixture must publish the exact BACKGROUND_TASK_DONE payload that
WebuiVoiceWorkNotifier consumes to emit the voice_background_task_done
SYSTEM_NOTIFICATION over SSE. This guards the contract from the fixture side.
"""

from __future__ import annotations

from importlib import import_module
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def fixture_app() -> FastAPI:
    app = FastAPI()
    module = import_module("app.api.background_tasks.test_fixtures")
    app.include_router(module.router, prefix="/api/v1/background-tasks")
    return app


@pytest.fixture
def client(init_test_database, fixture_app: FastAPI) -> TestClient:
    with TestClient(fixture_app) as test_client:
        yield test_client


def test_seed_endpoint_publishes_voice_background_done(client: TestClient) -> None:
    """The fixture must publish the exact event WebuiVoiceWorkNotifier consumes."""
    from app.services.event.app_event_bus import AppEventType, get_event_bus

    bus = get_event_bus()
    queue = bus.subscribe()
    try:
        with patch("app.api.background_tasks.test_fixtures.is_local_mode", return_value=True):
            resp = client.post("/api/v1/background-tasks/test/seed-voice-done")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        chat_id = str(body["chat_id"])
        task_id = str(body["task_id"])
        assert chat_id.startswith("e2evoice")
        assert task_id.startswith("voice-e2e")

        found: dict[str, object] | None = None
        for _ in range(100):
            event = queue.get_nowait()
            if event.event_type == AppEventType.BACKGROUND_TASK_DONE:
                found = dict(event.data)
                break
        assert found is not None, "no BACKGROUND_TASK_DONE event published"
        assert found["background_source"] == "voice"
        assert found["source_chat_id"] == chat_id
        assert found["chat_id"] == chat_id
        assert found["task_id"] == task_id
        assert found["status"] == "completed"
        assert found["title"]
    finally:
        bus.unsubscribe(queue)
