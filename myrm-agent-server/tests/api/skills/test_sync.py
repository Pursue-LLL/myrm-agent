"""Integration tests for skill synchronization endpoints."""

import io
import json
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


def _export_zip(client: TestClient) -> bytes:
    response = client.get("/api/v1/skills/export")
    assert response.status_code == 200
    return response.content


def _import_zip(client: TestClient, zip_data: bytes) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp.write(zip_data)
        tmp.flush()
        with open(tmp.name, "rb") as f:
            files = {"file": ("test_backup.zip", f, "application/zip")}
            response = client.post("/api/v1/skills/import", files=files)
    os.unlink(tmp.name)
    assert response.status_code == 200
    return response.json()


def test_export_zip_contains_manifest(client: TestClient, mock_local_skills_dir: Path) -> None:
    """Export ZIP embeds a manifest with hash and version per skill."""
    skill_dir = mock_local_skills_dir / "manifested-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: manifested-skill\ndescription: test\nversion: 3\n---\n# Body", encoding="utf-8"
    )

    zip_data = _export_zip(client)
    with zipfile.ZipFile(io.BytesIO(zip_data), "r") as zf:
        assert "manifest.json" in zf.namelist()
        manifest = json.loads(zf.read("manifest.json"))

    assert manifest["format"] == "myrm-skills-backup"
    entry = next(s for s in manifest["skills"] if s["name"] == "manifested-skill")
    assert entry["version"] == 3
    assert len(entry["sha256"]) == 64
    assert entry["skill_id"]


def test_import_detects_hash_drift(client: TestClient, mock_local_skills_dir: Path) -> None:
    """A tampered ZIP (content drifted from its manifest) is reported as a mismatch."""
    skill_dir = mock_local_skills_dir / "drift-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: drift-skill\ndescription: test\n---\n# Original", encoding="utf-8")

    zip_data = _export_zip(client)

    # Tamper with the packaged SKILL.md but keep the original manifest.
    with zipfile.ZipFile(io.BytesIO(zip_data), "r") as zf:
        names = zf.namelist()
        payloads = {name: zf.read(name) for name in names if not name.endswith(".zip")}
    tampered = bytearray(payloads["drift-skill/SKILL.md"]) + b"\n# tampered"
    payloads["drift-skill/SKILL.md"] = bytes(tampered)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in payloads.items():
            zf.writestr(name, data)
    tampered_zip = buffer.getvalue()

    # Clear local copy first so the drifted payload gets imported.
    shutil.rmtree(skill_dir)
    result = _import_zip(client, tampered_zip)

    assert result["has_manifest"] is True
    assert result["hash_mismatch_count"] >= 1


def test_reimport_skips_unchanged_skills(client: TestClient, mock_local_skills_dir: Path) -> None:
    """Importing an identical backup reports unchanged_count instead of re-importing."""
    skill_dir = mock_local_skills_dir / "stable-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: stable-skill\ndescription: test\n---\n# Stable", encoding="utf-8")

    zip_data = _export_zip(client)

    # Remove the local copy so the first import restores it (imported_count > 0).
    shutil.rmtree(skill_dir)
    first = _import_zip(client, zip_data)
    assert first["imported_count"] >= 1
    assert first["unchanged_count"] == 0

    # A second import of the identical backup is a no-op.
    second = _import_zip(client, zip_data)
    assert second["unchanged_count"] >= 1
    assert second["imported_count"] == 0


def _zip_with_traversal(payload: dict[str, bytes]) -> bytes:
    """Build a ZIP whose member names try to escape the extraction dir."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in payload.items():
            zf.writestr(name, data)
    return buffer.getvalue()


@pytest.mark.parametrize(
    "member_name",
    [
        "../escape.md",
        "..\\escape.md",
        "/abs/path.md",
        "C:\\windows\\evil.md",
    ],
)
def test_import_rejects_zip_slip(client: TestClient, mock_local_skills_dir: Path, member_name: str) -> None:
    """A ZIP whose members escape the extraction dir is rejected with 400."""
    evil_zip = _zip_with_traversal({member_name: b"pwned"})

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp.write(evil_zip)
        tmp.flush()
        with open(tmp.name, "rb") as f:
            files = {"file": ("evil_backup.zip", f, "application/zip")}
            response = client.post("/api/v1/skills/import", files=files)
    os.unlink(tmp.name)

    assert response.status_code == 400
    assert "Unsafe archive member path" in response.json()["detail"]
