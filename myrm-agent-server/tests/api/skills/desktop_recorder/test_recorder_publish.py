"""Tests for the desktop recorder publish endpoint and skill-name normalization."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.skills.desktop_recorder import router
from app.api.skills.desktop_recorder.router import _normalize_skill_name


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/skills")
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def publish_env(tmp_path: Path):
    """Patch the skill store so publish writes into a temp directory."""
    config = MagicMock()
    config.local_skill_paths = [str(tmp_path)]
    user_config = MagicMock()
    user_config.get_config = AsyncMock(return_value=config)
    service = MagicMock()
    service.user_config = user_config
    with (
        patch("app.core.skills.store.service.skills_service", service),
        patch("app.core.skills.config_version.bump_skill_config_version", MagicMock()),
    ):
        yield tmp_path


def test_publish_writes_skill_markdown(client: TestClient, publish_env: Path) -> None:
    """Publishing writes SKILL.md into the resolved local skill path."""
    response = client.post(
        "/api/skills/desktop-recorder/publish",
        json={"session_id": "s1", "skill_name": "Weekly Export", "markdown_content": "# Skill\n"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["skill_id"] == "weekly_export"
    assert body["status"] == "published"
    written = Path(body["file_path"])
    assert written.name == "SKILL.md"
    assert written.read_text(encoding="utf-8") == "# Skill\n"
    assert written.parent.parent == publish_env


def test_publish_rejects_a_name_with_no_alphanumerics(client: TestClient, publish_env: Path) -> None:
    """A name that normalizes to nothing must be rejected rather than writing to the base dir."""
    response = client.post(
        "/api/skills/desktop-recorder/publish",
        json={"session_id": "s1", "skill_name": "!!!", "markdown_content": "# x"},
    )

    assert response.status_code == 400
    assert "Invalid skill name" in response.json()["detail"]


def test_publish_survives_a_version_bump_failure(client: TestClient, publish_env: Path) -> None:
    """An unavailable config-version bump must not fail an otherwise successful publish."""
    with patch(
        "app.core.skills.config_version.bump_skill_config_version",
        MagicMock(side_effect=RuntimeError("no config store")),
    ):
        response = client.post(
            "/api/skills/desktop-recorder/publish",
            json={"session_id": "s1", "skill_name": "Resilient", "markdown_content": "# y"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "published"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Weekly Export", "weekly_export"),
        ("  Spaced  ", "spaced"),
        ("Already_snake", "already_snake"),
        ("Multi---Dash", "multi_dash"),
        ("Tax2024", "tax2024"),
        ("2024Report", "skill_2024report"),
    ],
)
def test_normalize_skill_name(raw: str, expected: str) -> None:
    """Names become lowercase snake_case and never start with a digit."""
    assert _normalize_skill_name(raw) == expected


def test_normalize_skill_name_returns_empty_for_symbols_only() -> None:
    """A symbols-only name yields an empty string so the caller can reject it."""
    assert _normalize_skill_name("!!!") == ""
