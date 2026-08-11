"""Sandbox gate coverage for the skill history rollback endpoint.

Rollback rewrites skill content through the local skill write backend
(``SkillCreationService`` → ``~/.myrm/skills``), which the agent can never
load in sandbox mode. The endpoint must fail closed with 403 before any
write is attempted.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def history_client() -> TestClient:
    """Minimal app exposing only the skills history router."""
    from fastapi import FastAPI

    from tests.api.skills.conftest import _load_module_by_path

    app = FastAPI(title="Skills History Test App")
    history_module = _load_module_by_path("app.api.skills.history", "history.py")
    app.include_router(history_module.router, prefix="/api/v1/skills", tags=["skills-history"])
    return TestClient(app)


def test_rollback_blocked_in_sandbox(history_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rollback must fail closed with 403 in sandbox before any write."""
    from app.config.deploy_mode import get_deploy_mode
    from app.platform_utils.deployment_capabilities import (
        _reset_capabilities_cache_for_testing,
    )

    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()
    monkeypatch.setenv("DEPLOY_MODE", "sandbox")
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()

    rollback_to_version = AsyncMock()
    with (
        patch(
            "app.core.skills.store.service.skills_service.get_skill",
            return_value=SimpleNamespace(name="prebuilt-demo"),
        ),
        patch(
            "app.api.skills.history.history_skill_service",
            AsyncMock(rollback_to_version=rollback_to_version),
        ),
    ):
        resp = history_client.post(
            "/api/v1/skills/prebuilt-demo/rollback",
            json={"history_index": -1},
            headers={"X-User-ID": "test-user"},
        )

    assert resp.status_code == 403
    rollback_to_version.assert_not_awaited()

    monkeypatch.delenv("DEPLOY_MODE", raising=False)
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()


def test_rollback_allowed_in_local(history_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rollback proceeds to the write backend in local mode."""
    from app.config.deploy_mode import get_deploy_mode
    from app.platform_utils.deployment_capabilities import (
        _reset_capabilities_cache_for_testing,
    )
    from myrm_agent_harness.agent.skills.history.types import SkillRollbackResult

    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()
    monkeypatch.setenv("DEPLOY_MODE", "local")
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()

    rollback_to_version = AsyncMock(
        return_value=SkillRollbackResult(
            success=True,
            skill_name="prebuilt-demo",
            rolled_back_to=__import__("datetime").datetime.now(),
        )
    )
    with (
        patch(
            "app.core.skills.store.service.skills_service.get_skill",
            return_value=SimpleNamespace(name="prebuilt-demo"),
        ),
        patch(
            "app.api.skills.history.history_skill_service",
            AsyncMock(rollback_to_version=rollback_to_version),
        ),
    ):
        resp = history_client.post(
            "/api/v1/skills/prebuilt-demo/rollback",
            json={"history_index": -1},
            headers={"X-User-ID": "test-user"},
        )

    assert resp.status_code == 200
    rollback_to_version.assert_awaited_once()

    monkeypatch.delenv("DEPLOY_MODE", raising=False)
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()
