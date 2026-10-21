"""
[POS] tests/api/memory/test_memory_migration_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, pathlib.Path, app.api.memory.migration_router
[OUTPUT] test_bundle_export_and_restore_routes_are_gone, test_detect_competitor_assets_api, test_ingest_competitor_assets_api

Unit test suite for competitor asset detection and ingestion API endpoints.
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


def test_bundle_export_and_restore_routes_are_gone(
    migration_test_client: tuple[TestClient, Path],
) -> None:
    """Whole-instance backup moved to /instance-archive; the path-taking bundle routes must not exist."""
    client, _ = migration_test_client

    assert client.post("/api/memory/migration/export", json={}).status_code == 404
    assert client.post("/api/memory/migration/restore", json={}).status_code == 404


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
    assert (ingest_target / "memories" / "note.md").exists()
    assert (ingest_target / "rules" / "hermes_config.yaml").exists()
