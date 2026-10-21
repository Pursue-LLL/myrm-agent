"""Smoke tests for Memory Archive Restore HTTP routes.

Covers the four restore endpoints that were previously implemented in the
service + API layer but not mounted in the memory router. Guards against
regression where the feature silently returns 404.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.memory.router import router as memory_router


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(memory_router, prefix="/memory")
    return TestClient(app)


def test_archive_restore_dry_run_route_mounted() -> None:
    client = _build_client()
    # Empty body fails request validation (422) instead of 404, proving the
    # route is mounted on /memory/archive/restore/dry-run.
    response = client.post("/memory/archive/restore/dry-run", json={})
    assert response.status_code == 422


def test_archive_restore_confirm_route_mounted() -> None:
    client = _build_client()
    # Route is mounted (dependency manager failure surfaces as 500, never 404).
    response = client.post("/memory/archive/restore/confirm", json={})
    assert response.status_code != 404


def test_archive_restore_rollback_preview_route_mounted() -> None:
    client = _build_client()
    response = client.post("/memory/archive/restore/rollback/dry-run", json={})
    assert response.status_code == 422


def test_archive_restore_rollback_route_mounted() -> None:
    client = _build_client()
    response = client.post("/memory/archive/restore/rollback", json={})
    assert response.status_code != 404
