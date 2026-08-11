"""Sandbox gate coverage for the browser-recording skill generation endpoint.

``POST /browser/recording/generate-skill`` writes the generated skill to the
local skill store (~/.myrm/skills), which the agent can never load in sandbox
mode — the endpoint must fail closed with 403 before doing any work.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.browser_recording import router as browser_recording_router


@pytest.fixture
def recording_client() -> TestClient:
    """Minimal app exposing only the browser-recording router."""
    app = FastAPI(title="Browser Recording Test App")
    app.include_router(browser_recording_router, prefix="/browser")
    return TestClient(app)


def test_generate_skill_blocked_in_sandbox(
    recording_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Generate-skill must fail closed with 403 in sandbox before any session lookup."""
    from app.config.deploy_mode import get_deploy_mode
    from app.platform_utils.deployment_capabilities import (
        _reset_capabilities_cache_for_testing,
    )

    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()
    monkeypatch.setenv("DEPLOY_MODE", "sandbox")
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()

    resp = recording_client.post(
        "/browser/recording/generate-skill",
        json={"session_id": "sess-1", "skill_name": "my_skill"},
    )

    assert resp.status_code == 403

    monkeypatch.delenv("DEPLOY_MODE", raising=False)
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()


def test_generate_skill_missing_session_in_local(
    recording_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Local mode passes the gate and continues to session validation (404 here)."""
    from app.config.deploy_mode import get_deploy_mode
    from app.platform_utils.deployment_capabilities import (
        _reset_capabilities_cache_for_testing,
    )

    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()
    monkeypatch.setenv("DEPLOY_MODE", "local")
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()

    resp = recording_client.post(
        "/browser/recording/generate-skill",
        json={"session_id": "sess-missing", "skill_name": "my_skill"},
    )

    assert resp.status_code == 404

    monkeypatch.delenv("DEPLOY_MODE", raising=False)
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()
