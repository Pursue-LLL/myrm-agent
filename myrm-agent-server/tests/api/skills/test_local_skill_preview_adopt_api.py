"""Unit tests for local skill path preview and adopt endpoints."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.skills.local import router
from app.core.skills.models import Skill, SkillType, UserSkillConfig

app = FastAPI()
app.include_router(router, prefix="/api/skills")
client = TestClient(app)


@pytest.fixture
def sample_skill_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with a single valid skill."""
    skill_dir = tmp_path / "hello-skill"
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        "---\n"
        "name: hello-skill\n"
        "description: A friendly greeting skill\n"
        "version: 1.2.0\n"
        "category: automation\n"
        "metadata:\n"
        "  author: developer\n"
        "  tags: [greeting, utility]\n"
        "---\n"
        "# Hello Skill\n"
        "Prints a friendly greeting.\n",
        encoding="utf-8",
    )
    return skill_dir


@pytest.fixture
def parent_skills_dir(tmp_path: Path) -> Path:
    """Create a root directory containing multiple skill subdirectories."""
    root = tmp_path / "custom-skills"
    root.mkdir(parents=True)

    # Skill 1
    s1 = root / "skill-alpha"
    s1.mkdir()
    (s1 / "SKILL.md").write_text(
        "---\n"
        "name: skill-alpha\n"
        "description: Alpha worker\n"
        "version: 2.0.0\n"
        "---\n",
        encoding="utf-8",
    )

    # Skill 2
    s2 = root / "skill-beta"
    s2.mkdir()
    (s2 / "SKILL.md").write_text(
        "---\n" "name: skill-beta\n" "description: Beta runner\n" "---\n",
        encoding="utf-8",
    )

    # Subdir without SKILL.md (should be ignored)
    (root / "not-a-skill").mkdir()

    return root


def test_preview_single_skill_path(sample_skill_dir: Path) -> None:
    """Test previewing a direct skill directory."""
    resp = client.post(
        "/api/skills/local/paths/preview",
        json={"path": str(sample_skill_dir)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is True
    assert data["is_directory"] is True
    assert data["total_discovered"] == 1
    skill = data["skills"][0]
    assert skill["name"] == "hello-skill"
    assert skill["version"] == "1.2.0"
    assert skill["author"] == "developer"
    assert "greeting" in skill["tags"]
    assert skill["skill_id"].startswith("local::")
    assert skill["is_conflicted"] is False


def test_preview_parent_directory(parent_skills_dir: Path) -> None:
    """Test previewing a parent directory containing multiple skill subdirectories."""
    resp = client.post(
        "/api/skills/local/paths/preview",
        json={"path": str(parent_skills_dir)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is True
    assert data["is_directory"] is True
    assert data["total_discovered"] == 2
    names = {s["name"] for s in data["skills"]}
    assert names == {"skill-alpha", "skill-beta"}


def test_preview_nonexistent_path(tmp_path: Path) -> None:
    """Test previewing a non-existent directory."""
    non_existent = tmp_path / "does-not-exist"
    resp = client.post(
        "/api/skills/local/paths/preview",
        json={"path": str(non_existent)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is False
    assert data["is_directory"] is False
    assert data["total_discovered"] == 0
    assert data["warning_message"] == "Path does not exist"


def test_preview_invalid_path_format() -> None:
    """Test previewing with a relative path format (should return 400)."""
    resp = client.post(
        "/api/skills/local/paths/preview",
        json={"path": "relative/path/not/allowed"},
    )
    assert resp.status_code == 400
    assert "Must be absolute path or start with ~" in resp.json()["detail"]


def test_preview_conflict_detection(sample_skill_dir: Path) -> None:
    """Test detecting naming conflicts against already registered skills."""
    mock_existing_skill = Skill(
        id="prebuilt::hello-skill",
        type=SkillType.PREBUILT,
        name="hello-skill",
        description="Built-in greeting",
        storage_path="/path/to/hello-skill",
    )

    with patch(
        "app.core.skills.store.service.skills_service.list_skills",
        AsyncMock(return_value=[mock_existing_skill]),
    ):
        resp = client.post(
            "/api/skills/local/paths/preview",
            json={"path": str(sample_skill_dir)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_discovered"] == 1
        skill = data["skills"][0]
        assert skill["is_conflicted"] is True
        assert "Conflicts with existing prebuilt skill" in str(skill["conflict_reason"])


def test_adopt_local_skill_path(sample_skill_dir: Path) -> None:
    """Test adopting a local skill path and enabling selected skills."""
    mock_config = UserSkillConfig(
        user_id="test_user",
        local_skill_paths=[],
        enabled_local_skill_ids=[],
    )

    with (
        patch(
            "app.core.skills.store.service.skills_service.user_config.get_config",
            AsyncMock(return_value=mock_config),
        ),
        patch(
            "app.core.skills.store.service.skills_service.user_config.update_local_skill_paths",
            AsyncMock(return_value=mock_config),
        ) as mock_update_paths,
        patch(
            "app.core.skills.store.service.skills_service.user_config.enable_local_skill",
            AsyncMock(return_value=mock_config),
        ) as mock_enable_skill,
    ):
        target_skill_id = "local::1234567890abcdef"
        resp = client.post(
            "/api/skills/local/paths/adopt",
            json={
                "path": str(sample_skill_dir),
                "selected_skill_ids": [target_skill_id],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["path"] == str(sample_skill_dir)
        assert data["added_to_paths"] is True
        assert data["adopted_skills_count"] == 1
        assert data["adopted_skill_ids"] == [target_skill_id]

        mock_update_paths.assert_awaited_once_with([str(sample_skill_dir)])
        mock_enable_skill.assert_awaited_once_with(target_skill_id)


def test_adopt_with_agent_integration(sample_skill_dir: Path) -> None:
    """Test adopting a path with agent allowlist integration."""
    mock_config = UserSkillConfig(
        user_id="test_user",
        local_skill_paths=[str(sample_skill_dir)],
        enabled_local_skill_ids=[],
    )

    from app.core.skills.discovery.adopt import DiscoveryAdoptionResult

    mock_adopt_res = DiscoveryAdoptionResult(
        allowlist_appended=True,
        agent_id="test-agent-123",
    )

    with (
        patch(
            "app.core.skills.store.service.skills_service.user_config.get_config",
            AsyncMock(return_value=mock_config),
        ),
        patch(
            "app.core.skills.store.service.skills_service.user_config.enable_local_skill",
            AsyncMock(return_value=mock_config),
        ),
        patch(
            "app.core.skills.discovery.adopt.complete_discovery_adoption",
            AsyncMock(return_value=mock_adopt_res),
        ) as mock_agent_adopt,
    ):
        target_skill_id = "local::abcdef1234567890"
        resp = client.post(
            "/api/skills/local/paths/adopt",
            json={
                "path": str(sample_skill_dir),
                "selected_skill_ids": [target_skill_id],
                "agent_id": "test-agent-123",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["added_to_paths"] is False  # Already present
        assert data["agent_adopted"] is True
        assert data["agent_id"] == "test-agent-123"
        mock_agent_adopt.assert_awaited_once_with("test-agent-123", target_skill_id)
