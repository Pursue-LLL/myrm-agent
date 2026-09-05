"""Unit and integration tests for /api/v1/memory/head lightweight sequence probe."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from tests.support.minimal_app import build_minimal_app


@pytest.mark.asyncio
async def test_memory_head_probe_empty_db(db_session: AsyncSession) -> None:
    app = build_minimal_app(preset="memory")
    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.get("/api/v1/memory/head?since_seq=0")
        assert resp.status_code == 200
        data = resp.json()
        assert "head_seq" in data
        assert "has_changes" in data
        assert "server_time" in data


@pytest.mark.asyncio
async def test_memory_head_probe_with_data_and_lag_evaluation(db_session: AsyncSession) -> None:
    # Insert dummy conversation recall segments if schema exists or create table
    await db_session.execute(
        text(
            "CREATE TABLE IF NOT EXISTS conversation_recall_segments ("
            "id INTEGER PRIMARY KEY, chat_id TEXT, message_id TEXT, role TEXT, segment_text TEXT)"
        )
    )
    await db_session.execute(
        text(
            "INSERT OR REPLACE INTO conversation_recall_segments (id, chat_id, message_id, role, segment_text) "
            "VALUES (42, 'chat-probe', 'msg-probe', 'user', 'test snippet')"
        )
    )
    await db_session.commit()

    app = build_minimal_app(preset="memory")
    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # Case A: Downstream client has lag (since_seq=10 < head_seq=42)
        resp_lag = await client.get("/api/v1/memory/head?since_seq=10")
        assert resp_lag.status_code == 200
        data_lag = resp_lag.json()
        assert data_lag["head_seq"] >= 42
        assert data_lag["has_changes"] is True

        # Case B: Downstream client is up to date (since_seq=42 >= head_seq=42)
        resp_synced = await client.get(f"/api/v1/memory/head?since_seq={data_lag['head_seq']}")
        assert resp_synced.status_code == 200
        data_synced = resp_synced.json()
        assert data_synced["has_changes"] is False
