"""Integration tests for skill synchronization endpoints."""

import io
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_local_skills_dir(tmp_path: Path) -> Path:
    """Mock LOCAL_SKILLS_DIR to use a temporary directory."""
    import app.api.skills.sync as sync_module
    from app.core.skills.creation.service import skill_creation_service

    original_path = skill_creation_service.base_path

    # Use tmp_path
    test_path = tmp_path / "skills"
    test_path.mkdir(parents=True, exist_ok=True)

    skill_creation_service.base_path = test_path
    sync_module.LOCAL_SKILLS_DIR = test_path

    yield test_path

    # Restore
    skill_creation_service.base_path = original_path
    sync_module.LOCAL_SKILLS_DIR = original_path


def test_export_import_skills(client: TestClient, mock_local_skills_dir: Path) -> None:
    """Test exporting and importing skills via ZIP protocol."""
    # 1. Create a dummy skill
    skill_name = "dummy-skill-for-sync"
    skill_dir = mock_local_skills_dir / skill_name
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text("---\nname: dummy-skill\ndescription: test\n---\n# Test", encoding="utf-8")

    # 2. Export the skills
    response = client.get("/api/v1/skills/export")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "myrm_skills_backup_default.zip" in response.headers["content-disposition"]

    zip_data = response.content

    # Verify zip contents
    with zipfile.ZipFile(io.BytesIO(zip_data), "r") as zf:
        namelist = zf.namelist()
        assert any(f"{skill_name}/SKILL.md" in name for name in namelist)

    # 3. Delete the dummy skill locally to verify import works
    shutil.rmtree(skill_dir)
    assert not skill_dir.exists()

    # 4. Import the skills back
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp.write(zip_data)
        tmp.flush()

        with open(tmp.name, "rb") as f:
            files = {"file": ("test_backup.zip", f, "application/zip")}
            import_response = client.post("/api/v1/skills/import", files=files)

    os.unlink(tmp.name)

    assert import_response.status_code == 200
    res_json = import_response.json()
    assert res_json["status"] == "success"
    assert res_json["imported_count"] >= 1

    # Verify skill is back
    assert skill_dir.exists()
    assert skill_md.exists()
