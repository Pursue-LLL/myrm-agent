"""Integration & unit tests for SQLite database storage optimization API.

Tests cover:
- Database triplet (data.db, -wal, -shm) size aggregation
- Preflight disk headroom and active jobs safety gate
- Deep optimization (FTS optimize + VACUUM + WAL truncate) with backup rotation
- Light optimization (FTS optimize + WAL truncate) without VACUUM
- Validation and 409 conflict guard against active background jobs
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from tests.support.minimal_app import build_minimal_app


def _seed_test_database(db_file: Path) -> None:
    """Create a test SQLite database with a messages_fts table and dummy records."""
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, content TEXT)")
    cur.execute(
        """CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
            content,
            content=messages,
            content_rowid=id
        )"""
    )
    for i in range(100):
        cur.execute("INSERT INTO messages (content) VALUES (?)", (f"Message body text number {i} " * 5,))
        cur.execute("INSERT INTO messages_fts (rowid, content) VALUES (?, ?)", (i + 1, f"Message body text number {i} " * 5))
    conn.commit()
    conn.close()


@pytest.mark.asyncio
async def test_get_storage_info_with_sqlite_breakdown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify GET /storage returns aggregated db_breakdown including -wal and -shm."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    db_file = state_dir / "data.db"
    _seed_test_database(db_file)

    # Touch -wal and -shm files to simulate active WAL mode
    (state_dir / "data.db-wal").write_bytes(b"wal-bytes-padding" * 10)
    (state_dir / "data.db-shm").write_bytes(b"shm-bytes-padding")

    monkeypatch.setattr("app.config.settings.settings.database.state_dir", str(state_dir))

    app = build_minimal_app(preset="system")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api/v1") as client:
        res = await client.get("/system/storage")
        assert res.status_code == 200
        data = res.json()
        assert "db_breakdown" in data
        breakdown = data["db_breakdown"]
        assert breakdown["main_db_bytes"] > 0
        assert breakdown["wal_bytes"] == len(b"wal-bytes-padding" * 10)
        assert breakdown["shm_bytes"] == len(b"shm-bytes-padding")
        assert breakdown["total_bytes"] == (
            breakdown["main_db_bytes"] + breakdown["wal_bytes"] + breakdown["shm_bytes"]
        )

        # Check subdirs has data.db with total triplet bytes
        data_db_sub = next((s for s in data["subdirs"] if s["name"] == "data.db"), None)
        assert data_db_sub is not None
        assert data_db_sub["bytes"] == breakdown["total_bytes"]


@pytest.mark.asyncio
async def test_optimize_storage_preflight_safe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify preflight detects adequate disk headroom and recommends deep mode."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    _seed_test_database(state_dir / "data.db")

    monkeypatch.setattr("app.config.settings.settings.database.state_dir", str(state_dir))
    monkeypatch.setattr("myrm_agent_harness.api.hooks.count_running_background_shell_jobs", lambda: 0)

    app = build_minimal_app(preset="system")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api/v1") as client:
        res = await client.post("/system/storage/optimize-preflight")
        assert res.status_code == 200
        data = res.json()
        assert data["is_safe_to_optimize"] is True
        assert data["recommended_mode"] in ("deep", "light")
        assert data["active_background_jobs"] == 0
        assert data["db_breakdown"]["total_bytes"] > 0


@pytest.mark.asyncio
async def test_optimize_storage_preflight_blocks_when_background_jobs_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify preflight flags is_safe_to_optimize=False when background shell jobs exist."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    _seed_test_database(state_dir / "data.db")

    monkeypatch.setattr("app.config.settings.settings.database.state_dir", str(state_dir))
    monkeypatch.setattr("myrm_agent_harness.api.hooks.count_running_background_shell_jobs", lambda: 2)

    app = build_minimal_app(preset="system")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api/v1") as client:
        res = await client.post("/system/storage/optimize-preflight")
        assert res.status_code == 200
        data = res.json()
        assert data["is_safe_to_optimize"] is False
        assert data["active_background_jobs"] == 2
        assert "active background job(s) running" in data["reason"]


@pytest.mark.asyncio
async def test_optimize_storage_deep_mode_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify deep optimization performs FTS optimize, VACUUM, and creates backup."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    db_file = state_dir / "data.db"
    _seed_test_database(db_file)

    # Delete half the messages to create reclaimable freelist pages
    conn = sqlite3.connect(str(db_file))
    conn.execute("DELETE FROM messages WHERE id > 50")
    conn.commit()
    conn.close()

    monkeypatch.setattr("app.config.settings.settings.database.state_dir", str(state_dir))
    monkeypatch.setattr("myrm_agent_harness.api.hooks.count_running_background_shell_jobs", lambda: 0)

    app = build_minimal_app(preset="system")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api/v1") as client:
        res = await client.post("/system/storage/optimize", json={"mode": "deep", "create_backup": True})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["mode"] == "deep"
        assert data["before_bytes"] > 0
        assert data["after_bytes"] > 0
        assert data["backup_path"] is not None
        assert Path(data["backup_path"]).exists()


@pytest.mark.asyncio
async def test_optimize_storage_light_mode_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify light optimization works without error and truncates WAL."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    _seed_test_database(state_dir / "data.db")

    monkeypatch.setattr("app.config.settings.settings.database.state_dir", str(state_dir))
    monkeypatch.setattr("myrm_agent_harness.api.hooks.count_running_background_shell_jobs", lambda: 0)

    app = build_minimal_app(preset="system")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api/v1") as client:
        res = await client.post("/system/storage/optimize", json={"mode": "light", "create_backup": False})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["mode"] == "light"
        assert data["backup_path"] is None


@pytest.mark.asyncio
async def test_optimize_storage_validation_and_conflict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify invalid mode returns 400 and active background jobs return 409."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    _seed_test_database(state_dir / "data.db")

    monkeypatch.setattr("app.config.settings.settings.database.state_dir", str(state_dir))
    monkeypatch.setattr("myrm_agent_harness.api.hooks.count_running_background_shell_jobs", lambda: 0)

    app = build_minimal_app(preset="system")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api/v1") as client:
        # Invalid mode
        res_bad = await client.post("/system/storage/optimize", json={"mode": "invalid_mode"})
        assert res_bad.status_code == 400

        # Active jobs conflict
        monkeypatch.setattr("myrm_agent_harness.api.hooks.count_running_background_shell_jobs", lambda: 1)
        res_conflict = await client.post("/system/storage/optimize", json={"mode": "deep"})
        assert res_conflict.status_code == 409
        assert "Cannot optimize database while 1 background job(s) are active" in res_conflict.json()["detail"]
