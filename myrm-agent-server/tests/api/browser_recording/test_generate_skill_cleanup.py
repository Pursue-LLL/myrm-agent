"""Generate-skill success path: the recording session is released eagerly.

Once a skill is saved the recording session is never referenced again, so the
endpoint removes it from the in-memory registry instead of waiting for the
30-minute TTL prune.
"""

from __future__ import annotations

import importlib
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.browser_recording import router as browser_recording_router
from app.config.deploy_mode import get_deploy_mode
from app.platform_utils.deployment_capabilities import (
    _reset_capabilities_cache_for_testing,
)
from app.services.browser_recording import session_manager


@pytest.fixture
def recording_client() -> TestClient:
    """Minimal app exposing only the browser-recording router."""
    app = FastAPI(title="Browser Recording Test App")
    app.include_router(browser_recording_router, prefix="/browser")
    return TestClient(app)


@pytest.fixture
def local_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the endpoint in local deploy mode (gate passes)."""
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()
    monkeypatch.setenv("DEPLOY_MODE", "local")
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()
    yield
    monkeypatch.delenv("DEPLOY_MODE", raising=False)
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()


def _make_stopped_session(session_id: str) -> None:
    """Register a stopped session with one click step."""
    from myrm_agent_harness.toolkits.browser.action_capture import (
        ActionStep,
        ActionType,
        CaptureSession,
    )

    session = CaptureSession(session_id=session_id, status="stopped")
    session.add_step(
        ActionStep(
            seq=1,
            action=ActionType.CLICK,
            selector="#btn",
            url="https://example.com",
        )
    )
    session_manager.register_session(session)


def test_generate_skill_success_removes_session(
    recording_client: TestClient, local_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A successful save releases the recording session from the registry."""
    _make_stopped_session("sess-ok")

    br_router = importlib.import_module("app.api.browser_recording.router")
    monkeypatch.setattr(
        br_router,
        "generate_skill_from_session",
        lambda session, skill_name, description: ("---\n", "content", []),
    )

    class FakeSaveResult:
        success = True
        skill_id = "skill-1"
        error = None

    from app.core.skills.creation.service import SkillCreationService

    monkeypatch.setattr(
        SkillCreationService,
        "save_skill",
        AsyncMock(return_value=FakeSaveResult()),
    )

    resp = recording_client.post(
        "/browser/recording/generate-skill",
        json={
            "session_id": "sess-ok",
            "skill_name": "my_skill",
            "description": "test",
        },
    )

    assert resp.status_code == 200
    assert resp.json()["skill_id"] == "skill-1"
    assert session_manager.get_session("sess-ok") is None


def test_generate_skill_failure_keeps_session(
    recording_client: TestClient, local_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed save must keep the session so the user can retry."""
    _make_stopped_session("sess-retry")

    br_router = importlib.import_module("app.api.browser_recording.router")
    monkeypatch.setattr(
        br_router,
        "generate_skill_from_session",
        lambda session, skill_name, description: ("---\n", "content", []),
    )

    class FailedSaveResult:
        success = False
        skill_id = None
        error = "Invalid skill name: bad name"

    from app.core.skills.creation.service import SkillCreationService

    monkeypatch.setattr(
        SkillCreationService,
        "save_skill",
        AsyncMock(return_value=FailedSaveResult()),
    )

    resp = recording_client.post(
        "/browser/recording/generate-skill",
        json={
            "session_id": "sess-retry",
            "skill_name": "my_skill",
            "description": "test",
        },
    )

    assert resp.status_code == 500
    assert resp.json()["detail"] == "Invalid skill name: bad name"
    assert session_manager.get_session("sess-retry") is not None
