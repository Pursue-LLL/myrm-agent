"""
[POS] tests/api/memory/test_memory_migration_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, pathlib.Path, app.api.memory.migration_router
[OUTPUT] test_export_sovereign_bundle_api, test_restore_sovereign_bundle_api, test_detect_competitor_assets_api, test_ingest_competitor_assets_api

Unit test suite for sovereign asset migration, restore, and competitor ingestion API endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.migration_router import router as memory_migration_router
from app.services.memory.memory_migration_service import (
    MemoryMigrationService,
    get_memory_migration_service,
)


@pytest.fixture
def migration_test_client() -> Generator[tuple[TestClient, Path], None, None]:
    """Provide isolated TestClient mounting memory migration router with a mock root storage directory."""
    with tempfile.TemporaryDirectory() as td:
        storage_path = Path(td).resolve()
        service = MemoryMigrationService(default_storage_dir=storage_path)

        test_app = FastAPI()
        test_app.include_router(memory_migration_router, prefix="/api/memory")
        test_app.dependency_overrides[get_memory_migration_service] = lambda: service

        with TestClient(test_app) as client:
            yield client, storage_path


def test_export_sovereign_bundle_api(
    migration_test_client: tuple[TestClient, Path],
) -> None:
    """Verify POST /api/memory/migration/export collects assets and produces .myrmpkg archive."""
    client, storage_path = migration_test_client

    # Populate mock assets in storage
    wiki_dir = storage_path / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    (wiki_dir / "Architecture.md").write_text("# Core Architecture\nImportant details.", encoding="utf-8")

    skills_dir = storage_path / "skills" / "tester"
    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "test.py").write_text("print('running test')", encoding="utf-8")

    out_bundle = storage_path / "my_backup.myrmpkg"

    payload = {
        "source_dir": str(storage_path),
        "output_bundle_path": str(out_bundle),
        "include_categories": ["wiki_memory", "custom_skill"],
        "custom_description": "Myrm export API test",
    }

    resp = client.post("/api/memory/migration/export", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["success"] is True
    assert data["package_id"].startswith("myrmpkg-")
    assert data["asset_count"] >= 2
    assert data["total_bytes"] > 0
    assert data["sha256"] != ""
    assert Path(data["bundle_path"]).exists()


def test_restore_sovereign_bundle_api(
    migration_test_client: tuple[TestClient, Path],
) -> None:
    """Verify POST /api/memory/migration/restore unpacks bundle and dynamically remaps paths."""
    client, storage_path = migration_test_client

    # 1. Create source with mock path reference
    src_dir = storage_path / "src_ws"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "wiki").mkdir(parents=True, exist_ok=True)
    (src_dir / "wiki" / "Doc.md").write_text(
        f"# Workspace Guide\nRef: {src_dir}/src/index.ts\nContent",
        encoding="utf-8",
    )

    bundle_path = storage_path / "restore_test.myrmpkg"
    export_resp = client.post(
        "/api/memory/migration/export",
        json={
            "source_dir": str(src_dir),
            "output_bundle_path": str(bundle_path),
            "include_categories": ["wiki_memory"],
        },
    )
    assert export_resp.status_code == 200

    # 2. Target restore directory
    target_dir = storage_path / "target_ws"
    target_dir.mkdir(parents=True, exist_ok=True)

    restore_payload = {
        "bundle_path": str(bundle_path),
        "target_destination_dir": str(target_dir),
        "current_workspace_root": str(target_dir),
        "overwrite_existing": True,
    }

    restore_resp = client.post("/api/memory/migration/restore", json=restore_payload)
    assert restore_resp.status_code == 200, restore_resp.text
    res_data = restore_resp.json()

    assert res_data["success"] is True
    assert res_data["remapped_paths_count"] >= 1
    assert "wiki/Doc.md" in res_data["restored_assets"]

    restored_doc = target_dir / "wiki" / "Doc.md"
    assert restored_doc.exists()
    content = restored_doc.read_text(encoding="utf-8")
    assert f"{target_dir}/src/index.ts" in content
    assert str(src_dir) not in content


def test_detect_competitor_assets_api(
    migration_test_client: tuple[TestClient, Path],
) -> None:
    """Verify GET /api/memory/migration/detect-competitors returns host probe report."""
    client, _ = migration_test_client

    resp = client.get("/api/memory/migration/detect-competitors")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data["detected_competitors"], list)


def test_ingest_competitor_assets_api(
    migration_test_client: tuple[TestClient, Path],
) -> None:
    """Verify POST /api/memory/migration/ingest-competitors translates Hermes and Claude Code assets."""
    client, storage_path = migration_test_client

    # Create mock Hermes assets
    hermes_root = storage_path / "mock_hermes"
    hermes_root.mkdir(parents=True, exist_ok=True)
    (hermes_root / "config.yaml").write_text("model: gpt-4o\n", encoding="utf-8")
    (hermes_root / "memories").mkdir(parents=True, exist_ok=True)
    (hermes_root / "memories" / "note.md").write_text("User prefers dark mode", encoding="utf-8")

    ingest_target = storage_path / "ingest_dest"
    ingest_target.mkdir(parents=True, exist_ok=True)

    payload = {
        "competitor": "hermes",
        "source_path": str(hermes_root),
        "target_destination_dir": str(ingest_target),
    }

    resp = client.post("/api/memory/migration/ingest-competitors", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["success"] is True
    assert data["imported_memories_count"] == 1
    assert data["imported_rules_count"] == 1
    assert (ingest_target / "wiki_memory_data" / "note.md").exists()
    assert (ingest_target / "rules" / "hermes_config.yaml").exists()
