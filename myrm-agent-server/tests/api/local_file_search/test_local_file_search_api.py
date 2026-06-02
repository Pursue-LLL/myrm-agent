"""API integration tests for local file search router.

Tests REST API endpoints for directory CRUD, indexing triggers, and stats.
Uses real FastAPI test client with real database.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.local_file_search.router import router


@pytest.fixture
def app():
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/local-file-search")
    return test_app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def real_directory():
    with tempfile.TemporaryDirectory(prefix="lfs_api_test_") as tmpdir:
        real_path = str(Path(tmpdir).resolve())
        (Path(real_path) / "document.md").write_text(
            "# Architecture Decision Record\n\n"
            "## Context\n\n"
            "We need to choose a database for our new microservice. "
            "The service will handle approximately 10,000 requests per second "
            "with a mix of read and write operations.\n\n"
            "## Decision\n\n"
            "We chose PostgreSQL with connection pooling via PgBouncer.\n\n"
            "## Consequences\n\n"
            "This gives us strong ACID compliance and excellent query performance.\n"
        )
        yield real_path


class TestGetConfig:
    def test_get_config_empty(self, client):
        response = client.get("/api/local-file-search")
        assert response.status_code == 200
        data = response.json()
        assert "directories" in data
        assert "stats" in data

    def test_get_stats(self, client):
        response = client.get("/api/local-file-search/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("idle", "indexing", "failed")
        assert "total_files" in data


class TestDirectoryCRUD:
    def test_add_directory(self, client, real_directory):
        response = client.post(
            "/api/local-file-search/directories",
            json={"path": real_directory, "recursive": True},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["path"] == real_directory
        assert data["recursive"] is True
        assert data["enabled"] is True
        assert "id" in data

    def test_add_directory_nonexistent(self, client):
        response = client.post(
            "/api/local-file-search/directories",
            json={"path": "/nonexistent/path/12345"},
        )
        assert response.status_code == 400

    def test_update_directory(self, client, real_directory):
        add_resp = client.post(
            "/api/local-file-search/directories",
            json={"path": real_directory},
        )
        dir_id = add_resp.json()["id"]

        update_resp = client.patch(
            f"/api/local-file-search/directories/{dir_id}",
            json={"enabled": False},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["enabled"] is False

    def test_update_nonexistent_directory(self, client):
        response = client.patch(
            "/api/local-file-search/directories/nonexistent-id",
            json={"enabled": False},
        )
        assert response.status_code == 404

    def test_remove_directory(self, client, real_directory):
        add_resp = client.post(
            "/api/local-file-search/directories",
            json={"path": real_directory},
        )
        dir_id = add_resp.json()["id"]

        del_resp = client.delete(f"/api/local-file-search/directories/{dir_id}")
        assert del_resp.status_code == 204

    def test_remove_nonexistent_directory(self, client):
        response = client.delete("/api/local-file-search/directories/nonexistent-id")
        assert response.status_code == 404


class TestIndexTrigger:
    def test_trigger_index_no_directories(self, client):
        response = client.post("/api/local-file-search/index")
        assert response.status_code == 400
