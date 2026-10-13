import io
import json
import sqlite3
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.system.router import router
from app.services.system.takeout_service import UserTakeoutService


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/system")
    return TestClient(app)


def test_export_personal_data_takeout_api_success(client):
    """Test successful export of full personal data takeout archive."""
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"version": "1.0.0", "format": "myrm-takeout"}))
        zf.writestr("db/data.db", b"fake-sqlite-bytes")

    fake_zip_bytes = zip_buf.getvalue()

    with patch(
        "app.services.system.takeout_service.UserTakeoutService.build_takeout_zip",
        new_callable=AsyncMock,
    ) as mock_build:
        mock_build.return_value = fake_zip_bytes

        response = client.get("/api/v1/system/takeout?include_db=true&include_wiki=true")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert "attachment; filename=" in response.headers.get("content-disposition", "")
        assert response.headers.get("x-takeout-version") == "1.0.0"

        downloaded_zip = zipfile.ZipFile(io.BytesIO(response.content))
        file_list = downloaded_zip.namelist()
        assert "manifest.json" in file_list
        assert "db/data.db" in file_list

        mock_build.assert_awaited_once_with(
            include_db=True,
            include_wiki=True,
            include_skills=True,
            include_deliverables=True,
        )


def test_export_personal_data_takeout_api_failure(client):
    """Test 500 error handling when takeout archive generation fails."""
    with patch(
        "app.services.system.takeout_service.UserTakeoutService.build_takeout_zip",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Storage disk I/O failure"),
    ):
        response = client.get("/api/v1/system/takeout")
        assert response.status_code == 500
        assert "Failed to generate personal data takeout archive" in response.text


@pytest.mark.asyncio
async def test_user_takeout_service_build_zip(tmp_path: Path):
    """Test UserTakeoutService file assembly and online SQLite backup."""
    # Create temporary state directory
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True)

    # 1. Create a dummy sqlite db
    db_path = state_dir / "data.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);")
    conn.execute("INSERT INTO users (name) VALUES ('alice');")
    conn.commit()
    conn.close()

    # 2. Create wiki files
    wiki_dir = state_dir / "wiki"
    wiki_dir.mkdir()
    (wiki_dir / "note.md").write_text("# My Wiki Note", encoding="utf-8")

    # 3. Create skills files
    skills_dir = state_dir / "skills"
    skills_dir.mkdir()
    (skills_dir / "skill.yaml").write_text("name: custom-skill", encoding="utf-8")

    # Mock settings.database.state_dir
    with patch("app.services.system.takeout_service.get_settings") as mock_settings:
        mock_settings.return_value.database.state_dir = str(state_dir)

        zip_bytes = await UserTakeoutService.build_takeout_zip()

        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        namelist = zf.namelist()

        assert "manifest.json" in namelist
        assert "db/data.db" in namelist
        assert "wiki/note.md" in namelist
        assert "skills/skill.yaml" in namelist

        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert manifest["format"] == "myrm-takeout"
        assert "db" in manifest["contents"]
        assert manifest["contents"]["wiki"]["file_count"] == 1
        assert manifest["contents"]["skills"]["file_count"] == 1
