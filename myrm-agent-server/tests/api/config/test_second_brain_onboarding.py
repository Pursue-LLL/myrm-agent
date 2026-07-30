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
from app.services.wiki.vault_resolver import seed_agent_vault_from_default, vault_has_wiki_content
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


@pytest.fixture(autouse=True)
def clear_second_brain_preset_config():
    async def _clear() -> None:
        from app.services.config.service import config_service

        await config_service.delete("secondBrainPreset")

    asyncio.run(_clear())
    yield
    asyncio.run(_clear())


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


def _dual_cron_mock_mgr(
    *,
    list_jobs: list[SimpleNamespace] | None = None,
    create_side_effect: object | None = None,
) -> SimpleNamespace:
    read_later_job = SimpleNamespace(
        id="cron-read-later-1",
        name="Second Brain · Read-it-Later",
        agent_id="agent-second-brain-1",
    )
    delta_job = SimpleNamespace(
        id="cron-wiki-delta-1",
        name="Second Brain · Wiki Morning Delta",
        agent_id="agent-second-brain-1",
    )

    async def _get_job(job_id: str, _user_id: str) -> SimpleNamespace | None:
        if job_id == read_later_job.id:
            return read_later_job
        if job_id == delta_job.id:
            return delta_job
        return None

    create_job = AsyncMock(
        side_effect=create_side_effect,
    )
    if create_side_effect is None:
        create_job = AsyncMock(side_effect=[read_later_job, delta_job])

    return SimpleNamespace(
        list_jobs=AsyncMock(return_value=list_jobs or []),
        get_job=AsyncMock(side_effect=_get_job),
        create_job=create_job,
        update_job=AsyncMock(),
        delete_job=AsyncMock(return_value=True),
    )


def test_seed_agent_vault_from_default_copies_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config.settings import settings

    harness_dir = tmp_path / "harness"
    monkeypatch.setattr(settings.database, "harness_dir", str(harness_dir))

    default_raw = harness_dir / "wiki" / "agents" / "default" / "raw"
    default_raw.mkdir(parents=True)
    note_path = default_raw / "migration-note.md"
    note_path.write_text("# Migration note\n", encoding="utf-8")

    result = seed_agent_vault_from_default("agent-second-brain-1")
    assert result.skipped is False
    assert result.files_copied == 1
    copied_note = harness_dir / "wiki" / "agents" / "agent-second-brain-1" / "raw" / "migration-note.md"
    assert copied_note.is_file()
    assert vault_has_wiki_content("agent-second-brain-1") is True


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
    mock_mgr = _dual_cron_mock_mgr()
    created_profile = _mock_agent_profile()
    try:
        with (
            patch("app.core.security.auth.identity.is_loopback_ip", return_value=True),
            patch("app.services.onboarding.second_brain_preset.ensure_skills_enabled", new=AsyncMock()),
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
            patch(
                "app.services.onboarding.second_brain_preset.seed_agent_vault_from_default",
                return_value=SimpleNamespace(skipped=True, files_copied=0),
            ),
        ):
            client = TestClient(app)
            response = client.post("/api/v1/config/onboarding/second-brain/apply")
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["success"] is True
            assert payload["agent_id"] == "agent-second-brain-1"
            assert payload["cron_job_id"] == "cron-read-later-1"
            assert payload["delta_cron_job_id"] == "cron-wiki-delta-1"
            assert mock_mgr.create_job.call_count == 2
            assert any(item["id"] == "agent_tools" and item["ready"] for item in payload["checklist"])
            assert any(item["id"] == "cron_job" and item["ready"] for item in payload["checklist"])

            status_resp = client.get("/api/v1/config/onboarding/second-brain/status")
            assert status_resp.status_code == 200
            assert status_resp.json()["applied"] is True
    finally:
        app.router.lifespan_context = original_lifespan


def test_apply_second_brain_preset_idempotent_reuses_cron() -> None:
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    existing_read_later = SimpleNamespace(
        id="cron-existing-read",
        name="Second Brain · Read-it-Later",
        agent_id="agent-old",
    )
    existing_delta = SimpleNamespace(
        id="cron-existing-delta",
        name="Second Brain · Wiki Morning Delta",
        agent_id="agent-old",
    )
    async def _get_job(job_id: str, _user_id: str) -> SimpleNamespace:
        if job_id == "cron-existing-read":
            return existing_read_later
        return existing_delta

    mock_mgr = SimpleNamespace(
        list_jobs=AsyncMock(return_value=[existing_read_later, existing_delta]),
        get_job=AsyncMock(side_effect=_get_job),
        create_job=AsyncMock(),
        update_job=AsyncMock(),
        delete_job=AsyncMock(return_value=True),
    )
    profile = _mock_agent_profile()
    try:
        with (
            patch("app.core.security.auth.identity.is_loopback_ip", return_value=True),
            patch("app.services.onboarding.second_brain_preset.ensure_skills_enabled", new=AsyncMock()),
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
            patch(
                "app.services.onboarding.second_brain_preset.seed_agent_vault_from_default",
                return_value=SimpleNamespace(skipped=True, files_copied=0),
            ),
        ):
            client = TestClient(app)
            response = client.post("/api/v1/config/onboarding/second-brain/apply")
            assert response.status_code == 200, response.text
            mock_mgr.create_job.assert_not_called()
            assert mock_mgr.update_job.call_count == 2
    finally:
        app.router.lifespan_context = original_lifespan


def test_apply_second_brain_preset_rollback_on_cron_failure() -> None:
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    read_later_job = SimpleNamespace(
        id="cron-read-later-1",
        name="Second Brain · Read-it-Later",
        agent_id="agent-second-brain-1",
    )
    create_calls = {"count": 0}

    async def _create_job_side_effect(*_args: object, **_kwargs: object) -> SimpleNamespace:
        create_calls["count"] += 1
        if create_calls["count"] == 1:
            return read_later_job
        raise RuntimeError("cron create failed")

    mock_mgr = SimpleNamespace(
        list_jobs=AsyncMock(return_value=[]),
        get_job=AsyncMock(return_value=None),
        create_job=AsyncMock(side_effect=_create_job_side_effect),
        update_job=AsyncMock(),
        delete_job=AsyncMock(return_value=True),
    )
    created_profile = _mock_agent_profile()
    delete_agent = AsyncMock()
    try:
        with (
            patch("app.core.security.auth.identity.is_loopback_ip", return_value=True),
            patch("app.services.onboarding.second_brain_preset.ensure_skills_enabled", new=AsyncMock()),
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
            patch(
                "app.services.onboarding.second_brain_preset.AgentService.delete_agent",
                new=delete_agent,
            ),
            patch("app.services.onboarding.second_brain_preset.get_cron_manager", return_value=mock_mgr),
            patch(
                "app.services.onboarding.second_brain_preset.seed_agent_vault_from_default",
                return_value=SimpleNamespace(skipped=False, files_copied=1),
            ),
        ):
            client = TestClient(app)
            response = client.post("/api/v1/config/onboarding/second-brain/apply")
            assert response.status_code == 500
            delete_agent.assert_called_once_with("agent-second-brain-1")
            mock_mgr.delete_job.assert_called_once_with("cron-read-later-1", "default")
    finally:
        app.router.lifespan_context = original_lifespan


def test_apply_seeds_when_reusing_named_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config.settings import settings

    harness_dir = tmp_path / "harness"
    monkeypatch.setattr(settings.database, "harness_dir", str(harness_dir))

    default_raw = harness_dir / "wiki" / "agents" / "default" / "raw"
    default_raw.mkdir(parents=True)
    (default_raw / "existing-import.md").write_text("# Existing\n", encoding="utf-8")

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    mock_mgr = _dual_cron_mock_mgr()
    existing_profile = _mock_agent_profile()
    create_agent = AsyncMock()
    try:
        with (
            patch("app.core.security.auth.identity.is_loopback_ip", return_value=True),
            patch("app.services.onboarding.second_brain_preset.ensure_skills_enabled", new=AsyncMock()),
            patch(
                "app.services.agent.agent_service.AgentService.get_agents_by_name",
                new=AsyncMock(return_value=[existing_profile]),
            ),
            patch(
                "app.services.agent.agent_service.AgentService.get_agent_by_id",
                new=AsyncMock(return_value=existing_profile),
            ),
            patch(
                "app.services.agent.agent_service.AgentService.create_agent",
                new=create_agent,
            ),
            patch("app.services.onboarding.second_brain_preset.get_cron_manager", return_value=mock_mgr),
            patch(
                "app.services.onboarding.second_brain_preset._provider_is_ready",
                new=AsyncMock(return_value=True),
            ),
        ):
            client = TestClient(app)
            response = client.post("/api/v1/config/onboarding/second-brain/apply")
            assert response.status_code == 200, response.text
            create_agent.assert_not_called()
            seeded_note = harness_dir / "wiki" / "agents" / "agent-second-brain-1" / "raw" / "existing-import.md"
            assert seeded_note.is_file()
    finally:
        app.router.lifespan_context = original_lifespan


def test_apply_second_brain_preset_seeds_default_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config.settings import settings

    harness_dir = tmp_path / "harness"
    monkeypatch.setattr(settings.database, "harness_dir", str(harness_dir))

    default_raw = harness_dir / "wiki" / "agents" / "default" / "raw"
    default_raw.mkdir(parents=True)
    (default_raw / "obsidian-note.md").write_text("# Obsidian\n", encoding="utf-8")

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    mock_mgr = _dual_cron_mock_mgr()
    created_profile = _mock_agent_profile()
    try:
        with (
            patch("app.core.security.auth.identity.is_loopback_ip", return_value=True),
            patch("app.services.onboarding.second_brain_preset.ensure_skills_enabled", new=AsyncMock()),
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
            assert any(item["id"] == "vault_content" and item["ready"] for item in payload["checklist"])
            seeded_note = harness_dir / "wiki" / "agents" / "agent-second-brain-1" / "raw" / "obsidian-note.md"
            assert seeded_note.is_file()
    finally:
        app.router.lifespan_context = original_lifespan


def test_second_brain_status_clears_stale_agent_id() -> None:
    async def _seed_stale_preset() -> None:
        from app.services.config.service import config_service

        await config_service.set(
            config_key="secondBrainPreset",
            value={
                "agent_id": "deleted-agent-id",
                "agent_name": "Second Brain",
                "cron_job_id": "cron-read-later-1",
                "applied_at": "2026-01-01T00:00:00+00:00",
                "origin": "second_brain_preset",
            },
            device_id="test-stale-preset",
        )

    asyncio.run(_seed_stale_preset())

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    try:
        with (
            patch("app.core.security.auth.identity.is_loopback_ip", return_value=True),
            patch(
                "app.services.agent.agent_service.AgentService.get_agent_by_id",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.onboarding.second_brain_preset._provider_is_ready",
                new=AsyncMock(return_value=True),
            ),
        ):
            client = TestClient(app)
            response = client.get("/api/v1/config/onboarding/second-brain/status")
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["applied"] is False
            assert payload.get("agent_id") in (None, "")

            from app.services.config.service import config_service

            assert asyncio.run(config_service.get("secondBrainPreset")) is None
    finally:
        app.router.lifespan_context = original_lifespan


def test_apply_second_brain_message_includes_vault_seed_count() -> None:
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    mock_mgr = _dual_cron_mock_mgr()
    created_profile = _mock_agent_profile()
    try:
        with (
            patch("app.core.security.auth.identity.is_loopback_ip", return_value=True),
            patch("app.services.onboarding.second_brain_preset.ensure_skills_enabled", new=AsyncMock()),
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
            patch(
                "app.services.onboarding.second_brain_preset._provider_is_ready",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "app.services.onboarding.second_brain_preset.seed_agent_vault_from_default",
                return_value=SimpleNamespace(skipped=False, files_copied=3),
            ),
        ):
            client = TestClient(app)
            response = client.post("/api/v1/config/onboarding/second-brain/apply")
            assert response.status_code == 200, response.text
            payload = response.json()
            assert "3" in payload["message"]
            assert "wiki files" in payload["message"] or "wiki 文件" in payload["message"]
    finally:
        app.router.lifespan_context = original_lifespan


def test_apply_second_brain_wiki_morning_delta_uses_blueprint() -> None:
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    mock_mgr = _dual_cron_mock_mgr()
    created_profile = _mock_agent_profile()
    try:
        with (
            patch("app.core.security.auth.identity.is_loopback_ip", return_value=True),
            patch("app.services.onboarding.second_brain_preset.ensure_skills_enabled", new=AsyncMock()),
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
            patch(
                "app.services.onboarding.second_brain_preset._provider_is_ready",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "app.services.onboarding.second_brain_preset.seed_agent_vault_from_default",
                return_value=SimpleNamespace(skipped=True, files_copied=0),
            ),
        ):
            client = TestClient(app)
            response = client.post("/api/v1/config/onboarding/second-brain/apply")
            assert response.status_code == 200, response.text
            second_call = mock_mgr.create_job.await_args_list[1]
            assert second_call.args[1] == "Second Brain · Wiki Morning Delta"
            assert second_call.kwargs["tools_allowed"] == ("wiki", "memory", "file_ops")
            assert second_call.args[3].expr == "0 7 * * *"
    finally:
        app.router.lifespan_context = original_lifespan
