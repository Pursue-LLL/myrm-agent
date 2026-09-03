"""HTTP API tests for external agent transcript sync and status endpoints."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.memory.operations.external_transcripts import (
    router as external_transcripts_router,
)
from app.database.connection import get_db
from app.database.models import Base
from app.database.repositories.conversation_recall.sql import (
    CONVERSATION_RECALL_SCHEMA_SQL,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "test_claude_code_transcript.jsonl"
)


@pytest.fixture
def app_with_db(tmp_path: Path):
    app = FastAPI()
    app.include_router(external_transcripts_router, prefix="/api/v1/memory")

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test_api.db")

    async def init_schema():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            for ddl in CONVERSATION_RECALL_SCHEMA_SQL:
                await conn.execute(text(ddl))

    import asyncio

    asyncio.run(init_schema())

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_get_status_endpoint(app_with_db: TestClient) -> None:
    res = app_with_db.get("/api/v1/memory/external-transcripts/status")
    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is True
    assert "tracked_files_count" in data
    assert "default_directory" in data


def test_sync_with_directory_endpoint(app_with_db: TestClient, tmp_path: Path) -> None:
    test_dir = tmp_path / "transcripts"
    test_dir.mkdir()
    f1 = test_dir / "session.jsonl"
    f1.write_text(FIXTURE_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    res = app_with_db.post(
        "/api/v1/memory/external-transcripts/sync",
        json={"directory_path": str(test_dir), "source": "external:claude_code"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["synced_files"] == 1
    assert data["new_turns"] == 3
    assert len(data["affected_chats"]) == 1
    assert data["skipped_files"] == 0
    assert len(data["errors"]) == 0

    # Repeat sync should skip
    res2 = app_with_db.post(
        "/api/v1/memory/external-transcripts/sync",
        json={"directory_path": str(test_dir), "source": "external:claude_code"},
    )
    assert res2.status_code == 200
    assert res2.json()["synced_files"] == 0
    assert res2.json()["skipped_files"] == 1


def test_sync_with_uploaded_files_endpoint(app_with_db: TestClient) -> None:
    content = (
        json.dumps(
            {
                "type": "user",
                "message": {"role": "user", "content": "How to debug asyncio tasks?"},
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": "Use asyncio.current_task()",
                },
            }
        )
        + "\n"
    )

    payload = {
        "source": "external:codex",
        "uploaded_files": [{"filename": "uploaded_session.jsonl", "content": content}],
    }

    res = app_with_db.post("/api/v1/memory/external-transcripts/sync", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["synced_files"] == 1
    assert data["new_turns"] == 1
    assert len(data["affected_chats"]) == 1


def test_sync_invalid_directory_returns_error(app_with_db: TestClient) -> None:
    res = app_with_db.post(
        "/api/v1/memory/external-transcripts/sync",
        json={"directory_path": "/non/existent/directory/path/12345"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["synced_files"] == 0
    assert len(data["errors"]) > 0
    assert "Directory does not exist" in data["errors"][0]
