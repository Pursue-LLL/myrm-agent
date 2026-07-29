"""Tests for Second Brain onboarding preset endpoints."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.database.connection import init_database
from tests.support.minimal_app import build_minimal_app

TEST_WS = Path(os.environ["MYRM_DATA_DIR"])
TEST_DB = TEST_WS / "data.db"

app = build_minimal_app(preset="config")


@asynccontextmanager
async def _noop_lifespan(_app: object):
    yield


def _cleanup_db_files() -> None:
    TEST_DB.unlink(missing_ok=True)
    for suffix in ("-shm", "-wal", "-journal"):
        Path(f"{TEST_DB}{suffix}").unlink(missing_ok=True)


@pytest.fixture(scope="module", autouse=True)
def setup_test_database():
    asyncio.run(init_database())
    yield
    _cleanup_db_files()


def _mock_agent_profile(
    *,
    agent_id: str = "agent-second-brain-1",
    name: str = "Second Brain",
    tools: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=agent_id,
        display_name=name,
        built_in=False,
        tools_allowed=tools or ["web_search", "memory", "wiki", "cron", "structured_clarify"],
    )


def test_second_brain_status_before_apply() -> None:
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    try:
        with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
            client = TestClient(app)
            response = client.get("/api/v1/config/onboarding/second-brain/status")
            assert response.status_code == 200
            payload = response.json()
            assert payload["applied"] is False
            assert len(payload["checklist"]) == 4
    finally:
        app.router.lifespan_context = original_lifespan


def test_apply_second_brain_preset_success() -> None:
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    cron_job = SimpleNamespace(id="cron-read-later-1", name="Second Brain · Read-it-Later", agent_id="agent-second-brain-1")
    mock_mgr = SimpleNamespace(
        list_jobs=AsyncMock(return_value=[]),
        get_job=AsyncMock(return_value=cron_job),
        create_job=AsyncMock(return_value=cron_job),
        update_job=AsyncMock(),
        delete_job=AsyncMock(return_value=True),
    )
    created_profile = _mock_agent_profile()
    try:
        with (
            patch("app.core.security.auth.identity.is_loopback_ip", return_value=True),
            patch("app.services.onboarding.second_brain_preset._ensure_skills_enabled", new=AsyncMock()),
            patch(
                "app.services.agent.agent_service.AgentService.get_agents_by_name",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.services.agent.agent_service.AgentService.get_agent_by_id",
                new=AsyncMock(return_value=created_profile),
            ),
            patch(
                "app.services.agent.agent_service.AgentService.create_agent",
                new=AsyncMock(return_value=created_profile),
            ),
            patch("app.services.onboarding.second_brain_preset.get_cron_manager", return_value=mock_mgr),
            patch("app.services.onboarding.second_brain_preset._wiki_has_content", return_value=True),
            patch(
                "app.services.onboarding.second_brain_preset._provider_is_ready",
                new=AsyncMock(return_value=True),
            ),
        ):
            client = TestClient(app)
            response = client.post("/api/v1/config/onboarding/second-brain/apply")
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["success"] is True
            assert payload["agent_id"] == "agent-second-brain-1"
            assert payload["cron_job_id"] == "cron-read-later-1"
            assert any(item["id"] == "agent_tools" and item["ready"] for item in payload["checklist"])

            status_resp = client.get("/api/v1/config/onboarding/second-brain/status")
            assert status_resp.status_code == 200
            assert status_resp.json()["applied"] is True
    finally:
        app.router.lifespan_context = original_lifespan


def test_apply_second_brain_preset_idempotent_reuses_cron() -> None:
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    existing_cron = SimpleNamespace(id="cron-existing", name="Second Brain · Read-it-Later", agent_id="agent-old")
    mock_mgr = SimpleNamespace(
        list_jobs=AsyncMock(return_value=[existing_cron]),
        get_job=AsyncMock(return_value=existing_cron),
        create_job=AsyncMock(),
        update_job=AsyncMock(),
        delete_job=AsyncMock(return_value=True),
    )
    profile = _mock_agent_profile()
    try:
        with (
            patch("app.core.security.auth.identity.is_loopback_ip", return_value=True),
            patch("app.services.onboarding.second_brain_preset._ensure_skills_enabled", new=AsyncMock()),
            patch(
                "app.services.agent.agent_service.AgentService.get_agents_by_name",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.services.agent.agent_service.AgentService.get_agent_by_id",
                new=AsyncMock(return_value=profile),
            ),
            patch(
                "app.services.agent.agent_service.AgentService.create_agent",
                new=AsyncMock(return_value=profile),
            ),
            patch("app.services.onboarding.second_brain_preset.get_cron_manager", return_value=mock_mgr),
            patch("app.services.onboarding.second_brain_preset._wiki_has_content", return_value=False),
            patch(
                "app.services.onboarding.second_brain_preset._provider_is_ready",
                new=AsyncMock(return_value=False),
            ),
        ):
            client = TestClient(app)
            response = client.post("/api/v1/config/onboarding/second-brain/apply")
            assert response.status_code == 200, response.text
            mock_mgr.create_job.assert_not_called()
            mock_mgr.update_job.assert_called_once()
    finally:
        app.router.lifespan_context = original_lifespan
