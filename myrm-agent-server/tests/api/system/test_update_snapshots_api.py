from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.system.router import router
from app.services.system.update_snapshot_service import (
    UpdateSnapshotItem,
    _parse_manifest_label,
    create_pre_update_snapshot,
    list_update_snapshots,
)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/system")
    return TestClient(app)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    db_file = tmp_path / "data.db"
    connection = sqlite3.connect(str(db_file))
    try:
        connection.execute("CREATE TABLE chats (id INTEGER PRIMARY KEY, title TEXT)")
        connection.execute("INSERT INTO chats (title) VALUES ('hello')")
        connection.commit()
    finally:
        connection.close()
    return tmp_path


def test_parse_manifest_label() -> None:
    assert _parse_manifest_label("pre-update:v0.1.0->v0.2.0") == ("v0.1.0", "v0.2.0")
    assert _parse_manifest_label("Manual Snapshot") == (None, None)
    assert _parse_manifest_label("pre-update:broken") == (None, None)


def test_create_pre_update_snapshot_retains_five(data_dir: Path) -> None:
    for index in range(7):
        create_pre_update_snapshot(
            data_dir, from_version=f"v0.1.{index}", to_version="v0.2.0"
        )
    items = list_update_snapshots(data_dir)
    pre_update = [item for item in items if item.from_version is not None]
    assert len(pre_update) == 5
    assert all(item.to_version == "v0.2.0" for item in pre_update)


def test_list_snapshots_route(client) -> None:
    items = [
        UpdateSnapshotItem(
            snapshot_id="snap_1",
            label="pre-update:v0.1.0->v0.2.0",
            size_bytes=10,
            created_at="2026-09-27T00:00:00Z",
            from_version="v0.1.0",
            to_version="v0.2.0",
        )
    ]
    with patch(
        "app.services.system.update_snapshot_service.list_update_snapshots",
        return_value=items,
    ):
        response = client.get("/api/v1/system/storage/snapshots")
    assert response.status_code == 200
    payload = response.json()
    assert payload["snapshots"][0]["snapshot_id"] == "snap_1"
    assert payload["snapshots"][0]["to_version"] == "v0.2.0"


def test_restore_update_round_trips_both_dbs(client, data_dir: Path, monkeypatch) -> None:
    import importlib
    import types

    checkpoints = data_dir / "checkpoints.db"
    connection = sqlite3.connect(str(checkpoints))
    try:
        connection.execute("CREATE TABLE threads (id INTEGER PRIMARY KEY, state TEXT)")
        connection.execute("INSERT INTO threads (state) VALUES ('running')")
        connection.commit()
    finally:
        connection.close()

    system_router = importlib.import_module("app.api.system.router")
    stub_settings = types.SimpleNamespace(
        database=types.SimpleNamespace(state_dir=str(data_dir))
    )
    monkeypatch.setattr(system_router, "get_settings", lambda: stub_settings)

    created = client.post(
        "/api/v1/system/storage/snapshots/pre-update",
        json={"from_version": "v0.1.0", "to_version": "v0.2.0"},
    )
    assert created.status_code == 200
    snapshot_id = created.json()["snapshot_id"]

    listed = client.get("/api/v1/system/storage/snapshots")
    assert listed.status_code == 200
    entries = listed.json()["snapshots"]
    assert entries[0]["extra_files"] == ["checkpoints.db"]

    # Mutate both live DBs, then restore and verify contents return.
    live_main = sqlite3.connect(str(data_dir / "data.db"))
    try:
        live_main.execute("DELETE FROM chats")
        live_main.commit()
    finally:
        live_main.close()
    live_threads = sqlite3.connect(str(checkpoints))
    try:
        live_threads.execute("DELETE FROM threads")
        live_threads.commit()
    finally:
        live_threads.close()

    restored = client.post(f"/api/v1/system/storage/snapshots/{snapshot_id}/restore-update")
    assert restored.status_code == 200
    assert restored.json()["requires_restart"] is True

    check_main = sqlite3.connect(str(data_dir / "data.db"))
    try:
        rows = check_main.execute("SELECT title FROM chats").fetchall()
    finally:
        check_main.close()
    assert rows == [("hello",)]
    check_threads = sqlite3.connect(str(checkpoints))
    try:
        thread_rows = check_threads.execute("SELECT state FROM threads").fetchall()
    finally:
        check_threads.close()
    assert thread_rows == [("running",)]


def test_pre_update_route_validates_versions(client) -> None:
    response = client.post(
        "/api/v1/system/storage/snapshots/pre-update",
        json={"from_version": " ", "to_version": "v0.2.0"},
    )
    assert response.status_code == 400


def test_pre_update_route_creates_snapshot(client, data_dir: Path, monkeypatch) -> None:
    import importlib
    import types

    # NOTE: `app.api.system/__init__.py` re-exports the `router` object, so a
    # plain `import ...router as ...` binds the APIRouter instead of the module.
    system_router = importlib.import_module("app.api.system.router")

    stub_settings = types.SimpleNamespace(
        database=types.SimpleNamespace(state_dir=str(data_dir))
    )
    monkeypatch.setattr(system_router, "get_settings", lambda: stub_settings)
    response = client.post(
        "/api/v1/system/storage/snapshots/pre-update",
        json={"from_version": "v0.1.0", "to_version": "v0.2.0"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["from_version"] == "v0.1.0"
    assert payload["to_version"] == "v0.2.0"
    assert payload["label"] == "pre-update:v0.1.0->v0.2.0"
