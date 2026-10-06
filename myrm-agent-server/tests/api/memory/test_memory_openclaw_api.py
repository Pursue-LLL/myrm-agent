"""
[POS] tests/api/memory/test_memory_openclaw_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, pathlib.Path, sqlite3, tempfile, json, app.api.memory.openclaw_router
[OUTPUT] test_rescue_preview_healthy_database_api, test_rescue_preview_corrupted_file_api, test_import_v2_bundle_from_sqlite_api, test_import_v2_bundle_from_raw_payload_api

Unit test suite for OpenClaw 2.0 format translation, Swarm session trees, and SQLite crash recovery endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.openclaw_router import router as memory_openclaw_router
from app.services.memory.memory_openclaw_service import (
    MemoryOpenClawService,
    get_memory_openclaw_service,
)


@pytest.fixture
def openclaw_test_client() -> Generator[tuple[TestClient, MemoryOpenClawService], None, None]:
    """Provide isolated TestClient mounting OpenClaw memory router with a clean service instance."""
    service = MemoryOpenClawService()

    test_app = FastAPI()
    test_app.include_router(memory_openclaw_router, prefix="/api/memory")
    test_app.dependency_overrides[get_memory_openclaw_service] = lambda: service

    with TestClient(test_app) as client:
        yield client, service


def test_rescue_preview_healthy_database_api(
    openclaw_test_client: tuple[TestClient, MemoryOpenClawService],
) -> None:
    """Verify POST /api/memory/openclaw/rescue-preview inspects and previews salvageable records from SQLite."""
    client, _ = openclaw_test_client

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "openclaw_ok.sqlite"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE openclaw_v2_sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                parent_session_id TEXT,
                swarm_agent_id TEXT,
                owner_id TEXT,
                creator_id TEXT,
                messages TEXT,
                created_at TEXT
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE openclaw_v2_memories (
                id TEXT PRIMARY KEY,
                content TEXT,
                category TEXT,
                scope TEXT,
                target_agent_id TEXT,
                importance REAL,
                created_at TEXT
            );
            """
        )

        cursor.execute(
            "INSERT INTO openclaw_v2_sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
            (
                "sess-api-1",
                "Root Planning Session",
                None,
                None,
                "user_dan",
                "user_dan",
                json.dumps([{"role": "user", "content": "Deploy release"}]),
                "2026-09-03T09:00:00Z",
            ),
        )
        cursor.execute(
            "INSERT INTO openclaw_v2_memories VALUES (?, ?, ?, ?, ?, ?, ?);",
            (
                "mem-api-1",
                "Release target is 2026-10-15.",
                "timeline",
                "shared",
                None,
                0.9,
                "2026-09-03T09:01:00Z",
            ),
        )
        conn.commit()
        conn.close()

        req_payload = {"db_path": str(db_path)}
        resp = client.post("/api/memory/openclaw/rescue-preview", json=req_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["report"]["is_sqlite_corrupt"] is False
        assert data["report"]["recovered_count"] == 2
        assert len(data["sessions_preview"]) == 1
        assert data["sessions_preview"][0]["session_id"] == "sess-api-1"
        assert len(data["memories_preview"]) == 1
        assert data["memories_preview"][0]["entry_id"] == "mem-api-1"


def test_rescue_preview_corrupted_file_api(
    openclaw_test_client: tuple[TestClient, MemoryOpenClawService],
) -> None:
    """Verify POST /api/memory/openclaw/rescue-preview gracefully diagnoses corrupted file."""
    client, _ = openclaw_test_client

    with tempfile.TemporaryDirectory() as td:
        corrupt_path = Path(td) / "broken_sample.sqlite"
        corrupt_path.write_bytes(b"INVALID_HEADER_GARBAGE" * 20)

        req_payload = {"db_path": str(corrupt_path)}
        resp = client.post("/api/memory/openclaw/rescue-preview", json=req_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["report"]["is_sqlite_corrupt"] is True
        assert data["report"]["recovered_count"] == 0


def test_import_v2_bundle_from_sqlite_api(
    openclaw_test_client: tuple[TestClient, MemoryOpenClawService],
) -> None:
    """Verify POST /api/memory/openclaw/import-v2 ingests records from SQLite with Swarm hierarchy preserved."""
    client, _ = openclaw_test_client

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "openclaw_import.sqlite"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE openclaw_v2_sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                parent_session_id TEXT,
                swarm_agent_id TEXT,
                owner_id TEXT,
                creator_id TEXT,
                messages TEXT,
                created_at TEXT
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE openclaw_v2_memories (
                id TEXT PRIMARY KEY,
                content TEXT,
                category TEXT,
                scope TEXT,
                target_agent_id TEXT,
                importance REAL,
                created_at TEXT
            );
            """
        )

        cursor.execute(
            "INSERT INTO openclaw_v2_sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
            (
                "sess-child-10",
                "Worker Subagent Session",
                "sess-parent-1",
                "coder_subagent",
                "user_frank",
                "sess-parent-1",
                json.dumps([{"role": "assistant", "content": "Done"}]),
                "2026-09-03T11:00:00Z",
            ),
        )
        cursor.execute(
            "INSERT INTO openclaw_v2_memories VALUES (?, ?, ?, ?, ?, ?, ?);",
            (
                "mem-priv-10",
                "Private worker preferences: use async await.",
                "style",
                "private",
                "coder_subagent",
                0.8,
                "2026-09-03T11:02:00Z",
            ),
        )
        conn.commit()
        conn.close()

        req_payload = {
            "db_path": str(db_path),
            "default_scope_mode": "preserve",
        }
        resp = client.post("/api/memory/openclaw/import-v2", json=req_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["imported_sessions_count"] == 1
        assert data["imported_memories_count"] == 1
        assert data["rescue_report"] is not None
        assert data["rescue_report"]["recovered_count"] == 2


def test_import_v2_bundle_from_raw_payload_api(
    openclaw_test_client: tuple[TestClient, MemoryOpenClawService],
) -> None:
    """Verify POST /api/memory/openclaw/import-v2 ingests records from raw JSON dictionary payload."""
    client, _ = openclaw_test_client

    req_payload = {
        "raw_sessions": [
            {
                "session_id": "sess-raw-1",
                "title": "Raw Root Session",
                "owner_id": "user_grace",
                "messages": [{"content": "hello world"}],
            },
            {
                "session_id": "sess-raw-2",
                "title": "Raw Swarm Session",
                "parent_session_id": "sess-raw-1",
                "swarm_agent_id": "swarm_worker_7",
                "owner_id": "user_grace",
                "messages": [{"content": "working..."}],
            },
        ],
        "raw_memories": [
            {
                "entry_id": "mem-raw-1",
                "content": "User prefers concise answers.",
                "category": "preference",
                "scope": "shared",
            },
            {
                "entry_id": "mem-raw-2",
                "content": "Worker 7 state config.",
                "category": "state",
                "scope": "private",
                "target_agent_id": "swarm_worker_7",
            },
        ],
        "default_scope_mode": "preserve",
    }

    resp = client.post("/api/memory/openclaw/import-v2", json=req_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["imported_sessions_count"] == 2
    assert data["imported_memories_count"] == 2
    assert "2 OpenClaw sessions" in data["message"]
