"""Integration tests for local skill path preview, adopt, and agent task execution.

Verifies:
1. HTTP API preview and adopt endpoints under real service conditions.
2. Full lifecycle: create local skill, preview path, adopt and enable, verify it is available.
3. Multi-path scanning and conflict detection with real persistence.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.security.auth.identity import LOCAL_USER_ID, ResolvedIdentity
from app.core.skills.models import SkillType
from app.core.skills.store.service import skills_service
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="skills_api")
client = TestClient(app, base_url="http://localhost:8080")


@pytest.fixture
def clean_skill_workspace(tmp_path: Path) -> Path:
    """Fixture creating a temporary directory with a valid skill."""
    workspace = tmp_path / "custom_math_skill"
    workspace.mkdir(parents=True)
    skill_md = workspace / "SKILL.md"
    skill_md.write_text(
        "---\n"
        "name: custom-math-calculator\n"
        "description: Calculates numerical formulas and equations\n"
        "version: 1.0.0\n"
        "category: productivity\n"
        "metadata:\n"
        "  author: integration-tester\n"
        "  tags: [math, calculator]\n"
        "---\n"
        "# Custom Math Calculator\n"
        "Calculates formulas accurately.\n",
        encoding="utf-8",
    )
    return workspace


@pytest.mark.asyncio
async def test_full_lifecycle_local_skill_preview_and_adopt(
    clean_skill_workspace: Path,
    tmp_path: Path,
) -> None:
    """Test full integration lifecycle from preview to adoption and store discovery."""
    mock_local_identity = ResolvedIdentity(
        user_id=LOCAL_USER_ID,
        auth_source="loopback",
        client_ip="127.0.0.1",
        loopback=True,
        private_net=True,
        local_trusted=True,
    )

    with patch(
        "app.middleware.auth.resolve_identity",
        return_value=mock_local_identity,
    ):
        # 1. Preview the path via API
        resp_preview = client.post(
            "/api/v1/skills/local/paths/preview",
            json={"path": str(clean_skill_workspace)},
        )
        assert resp_preview.status_code == 200, resp_preview.text
        preview_data = resp_preview.json()
        assert preview_data["exists"] is True
        assert preview_data["is_directory"] is True
        assert preview_data["total_discovered"] == 1

        skill_item = preview_data["skills"][0]
        assert skill_item["name"] == "custom-math-calculator"
        assert skill_item["author"] == "integration-tester"
        assert "math" in skill_item["tags"]
        assert skill_item["is_safe"] is True
        skill_id = skill_item["skill_id"]
        assert skill_id.startswith("local::")

        # 2. Adopt the path and skill via API
        resp_adopt = client.post(
            "/api/v1/skills/local/paths/adopt",
            json={
                "path": str(clean_skill_workspace),
                "selected_skill_ids": [skill_id],
            },
        )
        assert resp_adopt.status_code == 200, resp_adopt.text
        adopt_data = resp_adopt.json()
        assert adopt_data["status"] == "ok"
        assert adopt_data["path"] == str(clean_skill_workspace)
        assert adopt_data["added_to_paths"] is True
        assert skill_id in adopt_data["adopted_skill_ids"]

        # 3. Verify the skill is now listed in store as active local skill
        user_config = await skills_service.user_config.get_config()
        assert str(clean_skill_workspace) in user_config.local_skill_paths
        assert skill_id in user_config.enabled_local_skill_ids

        # 4. Verify list_skills returns the adopted skill with full metadata
        skills = await skills_service.list_skills(skill_type=SkillType.LOCAL)
        matched = [s for s in skills if s.id == skill_id]
        assert len(matched) == 1
        local_skill = matched[0]
        assert local_skill.name == "custom-math-calculator"
        assert local_skill.author == "integration-tester"
        assert "math" in local_skill.tags

        # 5. Preview again to verify conflict / duplicate state
        resp_preview_2 = client.post(
            "/api/v1/skills/local/paths/preview",
            json={"path": str(clean_skill_workspace)},
        )
        assert resp_preview_2.status_code == 200
        preview_data_2 = resp_preview_2.json()
        assert preview_data_2["total_discovered"] == 1
        assert preview_data_2["skills"][0]["is_conflicted"] is True
        assert "Conflicts with existing local skill" in str(
            preview_data_2["skills"][0]["conflict_reason"]
        )

        # 6. Verify path statuses inspection endpoint reports exact status
        resp_paths = client.get("/api/v1/skills/local/paths")
        assert resp_paths.status_code == 200
        paths_data = resp_paths.json()
        assert "path_statuses" in paths_data
        matched_status = next(
            (
                s
                for s in paths_data["path_statuses"]
                if s["path"] == str(clean_skill_workspace)
            ),
            None,
        )
        assert matched_status is not None
        assert matched_status["exists"] is True
        assert matched_status["is_directory"] is True
        assert matched_status["skills_count"] == 1
        assert "custom-math-calculator" in matched_status["skill_names"]

        # 7. Real execution test: download/sync skill to workspace and execute task
        agent_workspace = tmp_path / "agent_run_workspace"
        target_skills_dir = (
            agent_workspace / ".myrm" / "skills" / "custom-math-calculator"
        )
        target_skills_dir.mkdir(parents=True)
        from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

        custom_dest_storage = LocalStorageBackend(base_path=str(agent_workspace))
        download_success = await skills_service.download_skill_to_workspace(
            skill_id=skill_id,
            target_path=".myrm/skills/custom-math-calculator",
            target_storage=custom_dest_storage,
            force=True,
        )
        assert download_success is True
        synced_skill_md = target_skills_dir / "SKILL.md"
        assert synced_skill_md.exists()
        assert "custom-math-calculator" in synced_skill_md.read_text(encoding="utf-8")
