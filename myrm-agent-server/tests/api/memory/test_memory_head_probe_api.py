"""Unit tests for /api/v1/memory/head lightweight sequence probe endpoint."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.memory.operations.head_probe import router as head_router
from app.database.connection import get_db


@pytest.fixture
async def probe_test_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        yield session
    await engine.dispose()


def test_memory_head_probe_empty_db(probe_test_session: AsyncSession) -> None:
    app = FastAPI()
    app.include_router(head_router, prefix="/api/v1/memory")
    app.dependency_overrides[get_db] = lambda: probe_test_session

    client = TestClient(app)
    resp = client.get("/api/v1/memory/head?since_seq=0")
    assert resp.status_code == 200
    data = resp.json()
    assert data["head_seq"] == 0
    assert data["has_changes"] is False
    assert "server_time" in data


@pytest.mark.asyncio
async def test_memory_head_probe_with_segments(probe_test_session: AsyncSession) -> None:
    # Create conversation_recall_segments table and insert rows
    await probe_test_session.execute(
        text("CREATE TABLE conversation_recall_segments (id INTEGER PRIMARY KEY, content TEXT)")
    )
    await probe_test_session.execute(
        text("INSERT INTO conversation_recall_segments (id, content) VALUES (1, 'recall item 1'), (15, 'recall item 15')")
    )
    await probe_test_session.commit()

    app = FastAPI()
    app.include_router(head_router, prefix="/api/v1/memory")
    app.dependency_overrides[get_db] = lambda: probe_test_session

    client = TestClient(app)

    # 1. Client lag behind
    resp1 = client.get("/api/v1/memory/head?since_seq=0")
    assert resp1.status_code == 200
    d1 = resp1.json()
    assert d1["head_seq"] == 15
    assert d1["has_changes"] is True

    # 2. Client caught up
    resp2 = client.get("/api/v1/memory/head?since_seq=15")
    assert resp2.status_code == 200
    d2 = resp2.json()
    assert d2["head_seq"] == 15
    assert d2["has_changes"] is False

    # 3. Client ahead
    resp3 = client.get("/api/v1/memory/head?since_seq=20")
    assert resp3.status_code == 200
    d3 = resp3.json()
    assert d3["head_seq"] == 15
    assert d3["has_changes"] is False


@pytest.mark.asyncio
async def test_memory_head_probe_with_messages_fallback(probe_test_session: AsyncSession) -> None:
    # Test messages table rowid probe fallback when segments table does not exist
    await probe_test_session.execute(
        text("CREATE TABLE messages (id INTEGER PRIMARY KEY, content TEXT)")
    )
    await probe_test_session.execute(
        text("INSERT INTO messages (id, content) VALUES (1, 'msg 1'), (42, 'msg 42')")
    )
    await probe_test_session.commit()

    app = FastAPI()
    app.include_router(head_router, prefix="/api/v1/memory")
    app.dependency_overrides[get_db] = lambda: probe_test_session

    client = TestClient(app)
    resp = client.get("/api/v1/memory/head?since_seq=40")
    assert resp.status_code == 200
    data = resp.json()
    assert data["head_seq"] == 42
    assert data["has_changes"] is True
