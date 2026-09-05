"""Unit and Integration tests for Local Skill Path Preview and Adoption APIs."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.skills.local import router as local_router
from app.core.skills.models import Skill, SkillType
from app.core.skills.providers.local import LocalSkillsProvider


@pytest.fixture(scope="function")
def app() -> FastAPI:
    test_app = FastAPI(title="Local Skills API Test App")
    test_app.include_router(local_router, prefix="/api/v1/skills", tags=["skills"])
    return test_app


@pytest.fixture(scope="function")
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_provider_preview_path_not_exists() -> None:
    provider = LocalSkillsProvider()
    resolved, exists, is_dir, items, warning = provider.preview_path("/non/existent/path/123456")
    assert not exists
    assert not is_dir
    assert items == []
    assert warning == "Path does not exist"


def test_provider_preview_single_skill_dir() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            """---
name: my-standalone-skill
description: Standalone local skill for testing
version: 1.2.0
category: coding
tags:
  - test
  - python
requires:
  bins:
    - python3
---
# Instructions
Run safely.
""",
            encoding="utf-8",
        )

        provider = LocalSkillsProvider()
        resolved, exists, is_dir, items, warning = provider.preview_path(str(tmp_path))
        assert exists
        assert is_dir
        assert warning is None
        assert len(items) == 1
        item = items[0]
        assert item["name"] == "my-standalone-skill"
        assert item["version"] == "1.2.0"
        assert item["category"] == "coding"
        assert item["tags"] == ["test", "python"]
        assert item["required_tools"] == ["python3"]
        assert item["is_conflicted"] is False
        assert item["is_safe"] is True


def test_provider_preview_parent_dir_with_sub_skills_and_conflict() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        sub1 = tmp_path / "skill-alpha"
        sub1.mkdir()
        (sub1 / "SKILL.md").write_text(
            """---
name: alpha-tool
description: Alpha tool description
version: 0.1.0
---
Alpha instructions
""",
            encoding="utf-8",
        )

        sub2 = tmp_path / "skill-beta"
        sub2.mkdir()
        (sub2 / "SKILL.md").write_text(
            """---
name: beta-tool
description: Beta tool description
version: 2.0.0
---
Beta instructions
""",
            encoding="utf-8",
        )

        existing_skill = Skill(
            id="prebuilt::alpha-tool",
            type=SkillType.PREBUILT,
            name="alpha-tool",
            description="Existing prebuilt skill",
            storage_path="skills/prebuilt/alpha-tool",
            version="1.0.0",
        )

        provider = LocalSkillsProvider()
        resolved, exists, is_dir, items, warning = provider.preview_path(
            str(tmp_path), existing_skills=[existing_skill]
        )
        assert exists
        assert is_dir
        assert len(items) == 2

        alpha = next(it for it in items if it["name"] == "alpha-tool")
        beta = next(it for it in items if it["name"] == "beta-tool")

        assert alpha["is_conflicted"] is True
        assert "Conflicts with existing prebuilt skill 'alpha-tool'" in str(alpha["conflict_reason"])
        assert beta["is_conflicted"] is False


def test_api_preview_local_skill_path_endpoint(client: TestClient) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "SKILL.md").write_text(
            """---
name: preview-api-skill
description: API test skill
version: 1.0.5
---
# Body
""",
            encoding="utf-8",
        )

        with (
            patch("app.api.skills.local.require_local_skills_capability") as mock_cap,
            patch("app.api.skills.local.skills_service.list_skills", new_callable=AsyncMock) as mock_list,
        ):
            mock_cap.return_value = None
            mock_list.return_value = []

            resp = client.post(
                "/api/v1/skills/local/paths/preview",
                json={"path": str(tmp_path)},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["exists"] is True
            assert data["is_directory"] is True
            assert data["total_discovered"] == 1
            assert data["skills"][0]["name"] == "preview-api-skill"
            assert data["skills"][0]["version"] == "1.0.5"


def test_api_preview_local_skill_path_invalid_format(client: TestClient) -> None:
    with patch("app.api.skills.local.require_local_skills_capability"):
        resp = client.post(
            "/api/v1/skills/local/paths/preview",
            json={"path": "invalid/relative/path"},
        )
        assert resp.status_code == 400
        assert "Invalid path format" in resp.json()["detail"]


def test_provider_scan_path_single_skill_dir() -> None:
    """Verify that scan_path correctly identifies a single skill root directory."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "SKILL.md").write_text(
            """---
name: root-skill
description: Single skill directly in root directory
version: 1.0.0
---
Instruction
""",
            encoding="utf-8",
        )

        provider = LocalSkillsProvider()
        skills = provider.scan_path(tmp_path)
        assert len(skills) == 1
        assert skills[0].name == "root-skill"
        assert skills[0].type == SkillType.LOCAL


def test_api_local_paths_status_inspection(client: TestClient) -> None:
    """Verify that get_local_skill_paths includes runtime path_statuses."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "SKILL.md").write_text(
            """---
name: status-inspected-skill
description: Inspect status test
version: 2.1.0
---
""",
            encoding="utf-8",
        )

        fake_config = AsyncMock()
        fake_config.local_skill_paths = [str(tmp_path), "/non/existent/path/999"]

        with (
            patch("app.api.skills.local.require_local_skills_capability"),
            patch("app.api.skills.local.skills_service.user_config.get_config", return_value=fake_config),
        ):
            resp = client.get("/api/v1/skills/local/paths")
            assert resp.status_code == 200
            data = resp.json()
            assert "path_statuses" in data
            statuses = data["path_statuses"]
            assert len(statuses) == 2

            valid_status = next(s for s in statuses if s["path"] == str(tmp_path))
            assert valid_status["exists"] is True
            assert valid_status["skills_count"] == 1
            assert "status-inspected-skill" in valid_status["skill_names"]

            invalid_status = next(s for s in statuses if s["path"] == "/non/existent/path/999")
            assert invalid_status["exists"] is False
            assert invalid_status["skills_count"] == 0

