"""Restore point routes of the system API: create, list, queue restore (applied at next start), delete."""

from __future__ import annotations

import importlib
import sqlite3
import types
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.system.router import router
from app.services.instance_archive import ArchivePaths


@pytest.fixture
def client(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # `app.api.system/__init__.py` re-exports the `router` object, so import the module explicitly.
    system_router = importlib.import_module("app.api.system.router")
    stub = types.SimpleNamespace(database=types.SimpleNamespace(state_dir=str(data_dir)))
    monkeypatch.setattr(system_router, "get_settings", lambda: stub)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/system")
    return TestClient(app)


def _write(db: Path, ddl: str, insert: str | None = None) -> None:
    connection = sqlite3.connect(db)
    try:
        connection.execute(ddl)
        if insert:
            connection.execute(insert)
        connection.commit()
    finally:
        connection.close()


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    main = tmp_path / "data.db"
    _write(main, "CREATE TABLE _schema_migrations (version INTEGER)", "INSERT INTO _schema_migrations VALUES (0)")
    _write(main, "CREATE TABLE chats (id INTEGER PRIMARY KEY, title TEXT)", "INSERT INTO chats (title) VALUES ('hello')")
    _write(
        tmp_path / "checkpoints.db",
        "CREATE TABLE threads (id INTEGER PRIMARY KEY, state TEXT)",
        "INSERT INTO threads (state) VALUES ('running')",
    )
    return tmp_path


def test_pre_update_point_lists_with_version_linkage_and_companion_db(client: TestClient) -> None:
    created = client.post("/api/v1/system/storage/snapshots/pre-update", json={"from_version": "v0.1.0", "to_version": "v0.2.0"})
    assert created.status_code == 200
    payload = created.json()
    assert payload["label"] == "pre-update:v0.1.0->v0.2.0"
    assert (payload["from_version"], payload["to_version"]) == ("v0.1.0", "v0.2.0")

    [entry] = client.get("/api/v1/system/storage/snapshots").json()["snapshots"]
    assert entry["snapshot_id"] == payload["snapshot_id"]
    assert entry["extra_files"] == ["checkpoints.db"]


def test_pre_update_route_validates_versions(client: TestClient) -> None:
    response = client.post("/api/v1/system/storage/snapshots/pre-update", json={"from_version": " ", "to_version": "v0.2.0"})
    assert response.status_code == 400


def test_pre_update_retention_keeps_five(client: TestClient) -> None:
    for index in range(7):
        client.post("/api/v1/system/storage/snapshots/pre-update", json={"from_version": f"v0.1.{index}", "to_version": "v0.2.0"})
    snapshots = client.get("/api/v1/system/storage/snapshots").json()["snapshots"]
    assert len([s for s in snapshots if s["from_version"]]) == 5


def test_restore_is_queued_for_the_next_start_and_never_touches_live_data(client: TestClient, data_dir: Path) -> None:
    snapshot_id = client.post("/api/v1/system/storage/snapshots", json={"label": "manual"}).json()["snapshot"]["snapshot_id"]
    live = sqlite3.connect(data_dir / "data.db")
    live.execute("DELETE FROM chats")
    live.commit()
    live.close()

    restored = client.post(f"/api/v1/system/storage/snapshots/{snapshot_id}/restore")

    assert restored.status_code == 200
    assert restored.json()["requires_restart"] is True
    assert ArchivePaths(data_dir).pending.exists()
    check = sqlite3.connect(data_dir / "data.db")
    assert check.execute("SELECT COUNT(*) FROM chats").fetchone() == (0,)  # applied only after the restart
    check.close()

    again = client.post(f"/api/v1/system/storage/snapshots/{snapshot_id}/restore")
    assert (again.status_code, again.json()["detail"]["code"]) == (409, "operation_pending")


def test_unknown_snapshot_is_a_404(client: TestClient) -> None:
    restore = client.post("/api/v1/system/storage/snapshots/snap_missing/restore")
    delete = client.delete("/api/v1/system/storage/snapshots/snap_missing")
    assert (restore.status_code, restore.json()["detail"]["code"]) == (404, "unknown_restore_point")
    assert delete.status_code == 404


def test_delete_removes_the_point(client: TestClient) -> None:
    snapshot_id = client.post("/api/v1/system/storage/snapshots", json={"label": "manual"}).json()["snapshot"]["snapshot_id"]
    assert client.delete(f"/api/v1/system/storage/snapshots/{snapshot_id}").status_code == 200
    assert client.get("/api/v1/system/storage/snapshots").json()["snapshots"] == []
