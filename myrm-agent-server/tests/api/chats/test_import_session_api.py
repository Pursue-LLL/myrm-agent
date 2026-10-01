"""Unit and integration tests for the /api/chats/import-transcript endpoint."""

from __future__ import annotations

import io
import json
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.chats.chat.import_session import router as import_session_router
from app.database.connection import get_db
from app.database.models import Base, Chat, Message


@pytest.fixture
async def test_db() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def client(test_db: AsyncSession) -> AsyncIterator[AsyncClient]:
    test_app = FastAPI()
    test_app.include_router(import_session_router, prefix="/api/chats")

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield test_db

    test_app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_import_transcript_json_success(client: AsyncClient, test_db: AsyncSession) -> None:
    lines = [
        json.dumps({"type": "system", "content": "System instruction"}),
        json.dumps({
            "type": "user",
            "message": {"content": "Fix null pointer in user_service.py"},
        }),
        json.dumps({
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "I will check user_service.py now."},
                    {"type": "tool_use", "name": "bash", "input": {"cmd": "git status"}},
                ]
            },
        }),
        json.dumps({
            "type": "tool_result",
            "name": "bash",
            "content": "On branch main\nChanges not staged for commit:\n  modified: user_service.py\n",
        }),
        json.dumps({
            "type": "assistant",
            "message": {"content": "Fixed by adding defensive None check."},
        }),
    ]
    raw_payload = "\n".join(lines)

    resp = await client.post(
        "/api/chats/import-transcript",
        json={
            "raw_content": raw_payload,
            "source_hint": "claude",
            "title_override": "Fix Null Pointer Bug",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["title"] == "Fix Null Pointer Bug"
    assert data["turns_count"] == 1
    assert data["reduction_ratio"] > 0.0

    chat_id = data["chat_id"]
    # Verify in DB
    chat_stmt = select(Chat).where(Chat.id == chat_id)
    chat_res = await test_db.execute(chat_stmt)
    chat = chat_res.scalars().first()
    assert chat is not None
    assert chat.is_incognito is False  # Guarantees first-class sidebar visibility
    assert chat.title == "Fix Null Pointer Bug"

    # Verify messages
    msg_stmt = select(Message).where(Message.chat_id == chat_id)
    msg_res = await test_db.execute(msg_stmt)
    messages = list(msg_res.scalars().all())
    assert len(messages) == 2
    user_msg = next(m for m in messages if m.role == "user")
    asst_msg = next(m for m in messages if m.role == "assistant")
    assert user_msg.content == "Fix null pointer in user_service.py"
    assert "[Tool]" in asst_msg.content
    assert "Fixed by adding defensive None check" in asst_msg.content


@pytest.mark.asyncio
async def test_import_transcript_file_success(client: AsyncClient, test_db: AsyncSession) -> None:
    lines = [
        json.dumps({"role": "user", "content": "Deploy microservice"}),
        json.dumps({"role": "assistant", "content": "Deploying now..."}),
    ]
    file_bytes = ("\n".join(lines)).encode("utf-8")

    files = {"file": ("hermes_session.jsonl", io.BytesIO(file_bytes), "application/jsonl")}
    resp = await client.post("/api/chats/import-transcript/file", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["turns_count"] == 1


@pytest.mark.asyncio
async def test_import_transcript_empty_payload(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/chats/import-transcript",
        json={"raw_content": "   "},
    )
    assert resp.status_code == 400
