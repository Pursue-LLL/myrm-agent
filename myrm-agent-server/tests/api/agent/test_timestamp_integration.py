"""Integration tests for timestamp handling (sent_at, sent_timezone)."""

import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Message
from app.services.chat.chat_service import ChatService


@pytest_asyncio.fixture
async def db_session():
    """Create in-memory SQLite database for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from app.database.migrations import ensure_raw_sql_schema

    await ensure_raw_sql_schema(engine)

    TestingSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with TestingSessionLocal() as session:

        @asynccontextmanager
        async def mock_get_session():
            yield session

        def mock_get_session_factory():
            return lambda: session

        with (
            patch(
                "app.database.repositories.uow.get_session_factory",
                mock_get_session_factory,
            ),
        ):
            yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_web_message_timestamp_persistence(db_session):
    """Test Web端消息timestamp正确持久化到数据库."""
    # 模拟前端发送的timestamp和timezone
    client_timestamp = time.time()
    client_timezone = "Asia/Shanghai"
    sent_at_utc = datetime.fromtimestamp(client_timestamp, tz=timezone.utc)

    # 创建并保存消息
    msg = await ChatService.ensure_chat_and_append_user_message(
        chat_id="test-chat-timestamp-001",
        content="今天周几？",
        sent_at=sent_at_utc,
        sent_timezone=client_timezone,
        message_id="test-msg-timestamp-001",
    )
    await db_session.commit()

    # 验证数据库字段
    assert msg.sent_at is not None
    assert msg.sent_timezone == client_timezone
    assert abs(msg.sent_at.timestamp() - client_timestamp) < 1.0  # 允许1秒误差
    assert msg.created_at is not None  # 服务器接收时间也应该存在

    # 从数据库重新加载验证持久化
    result = await db_session.execute(select(Message).where(Message.id == msg.id))
    loaded_msg = result.scalar_one()
    assert loaded_msg.sent_at is not None
    assert loaded_msg.sent_timezone == client_timezone


@pytest.mark.asyncio
async def test_chat_history_includes_timestamp_metadata(db_session):
    """Test 历史消息加载时包含sent_at和sent_timezone元数据."""
    # 创建带timestamp的消息
    client_timestamp = time.time()
    client_timezone = "America/New_York"
    sent_at_utc = datetime.fromtimestamp(client_timestamp, tz=timezone.utc)

    await ChatService.ensure_chat_and_append_user_message(
        chat_id="test-chat-history-001",
        content="Test message for history",
        sent_at=sent_at_utc,
        sent_timezone=client_timezone,
        message_id="test-msg-history-001",
    )
    await db_session.commit()

    # 加载历史
    history = await ChatService.load_web_chat_history(
        "test-chat-history-001",
    )

    # 验证历史消息包含timestamp元数据
    assert len(history) == 1
    role, content, meta = history[0]
    assert role == "human"
    assert "sent_at" in meta
    assert "sent_timezone" in meta
    assert meta["sent_timezone"] == client_timezone
    assert abs(meta["sent_at"] - client_timestamp) < 1.0


@pytest.mark.asyncio
async def test_timezone_drift_stability(db_session):
    """Test 用户切换时区后，历史消息timestamp保持不变（Cache稳定性）."""
    # 初始消息：上海时区
    ts1 = time.time()
    tz1 = "Asia/Shanghai"
    sent_at1 = datetime.fromtimestamp(ts1, tz=timezone.utc)

    await ChatService.ensure_chat_and_append_user_message(
        chat_id="test-chat-drift-001",
        content="Message in Shanghai",
        sent_at=sent_at1,
        sent_timezone=tz1,
        message_id="test-msg-drift-001",
    )
    await db_session.commit()

    # 第一次加载（上海时区）
    history1 = await ChatService.load_web_chat_history(
        "test-chat-drift-001",
    )
    _, _, meta1 = history1[0]

    # 用户切换到纽约时区，发送新消息
    ts2 = time.time()
    tz2 = "America/New_York"
    sent_at2 = datetime.fromtimestamp(ts2, tz=timezone.utc)

    await ChatService.append_message(
        chat_id="test-chat-drift-001",
        role="user",
        content="Message in New York",
        sent_at=sent_at2,
        sent_timezone=tz2,
        message_id="test-msg-drift-002",
    )
    await db_session.commit()

    # 第二次加载（现在是纽约时区）
    history2 = await ChatService.load_web_chat_history(
        "test-chat-drift-001",
    )

    # 关键验证：历史消息保持原始sent_timezone，不受当前时区影响
    assert len(history2) == 2
    _, _, meta_old = history2[0]
    _, _, meta_new = history2[1]

    # 旧消息仍然使用上海时区
    assert meta_old["sent_timezone"] == tz1
    assert meta_old["sent_at"] == pytest.approx(ts1, abs=1.0)

    # 新消息使用纽约时区
    assert meta_new["sent_timezone"] == tz2
    assert meta_new["sent_at"] == pytest.approx(ts2, abs=1.0)

    # 这确保了Prompt Cache的稳定性：历史消息的时间戳不会因用户时区变化而改变


@pytest.mark.asyncio
async def test_sent_at_vs_created_at_semantic(db_session):
    """Test sent_at (用户发送时间) 和 created_at (服务器接收时间) 的语义区分."""
    # 模拟网络延迟：用户发送时间早于服务器接收时间
    user_send_time = time.time() - 5.0  # 5秒前发送
    sent_at_utc = datetime.fromtimestamp(user_send_time, tz=timezone.utc)

    msg = await ChatService.ensure_chat_and_append_user_message(
        chat_id="test-chat-semantic-001",
        content="Delayed message",
        sent_at=sent_at_utc,
        sent_timezone="UTC",
        message_id="test-msg-semantic-001",
    )
    await db_session.commit()

    # sent_at 是用户发送时间（5秒前）
    sent_ts = (
        msg.sent_at.replace(tzinfo=timezone.utc).timestamp()
        if msg.sent_at.tzinfo is None
        else msg.sent_at.timestamp()
    )
    assert abs(sent_ts - user_send_time) < 0.5

    # created_at 是服务器接收时间（刚刚）
    created_ts = (
        msg.created_at.replace(tzinfo=timezone.utc).timestamp()
        if msg.created_at.tzinfo is None
        else msg.created_at.timestamp()
    )
    assert abs(created_ts - time.time()) < 2.0

    # sent_at 应该早于 created_at（网络延迟）
    assert sent_ts < created_ts


@pytest.mark.asyncio
async def test_duplicate_user_message_id_allocates_fresh_id(db_session):
    """Turn2 must not reuse Turn1 request message_id; duplicate ids get a fresh UUID."""
    duplicate_id = "test-msg-duplicate-001"
    sent_at_utc = datetime.now(timezone.utc)
    first = await ChatService.ensure_chat_and_append_user_message(
        chat_id="test-chat-dedup-001",
        content="Turn 1",
        sent_at=sent_at_utc,
        sent_timezone="UTC",
        message_id=duplicate_id,
    )
    second = await ChatService.ensure_chat_and_append_user_message(
        chat_id="test-chat-dedup-001",
        content="Turn 2",
        sent_at=sent_at_utc,
        sent_timezone="UTC",
        message_id=duplicate_id,
    )
    await db_session.commit()

    assert first.id == duplicate_id
    assert second.id != duplicate_id
    assert second.content == "Turn 2"

    result = await db_session.execute(
        select(Message).where(
            Message.chat_id == "test-chat-dedup-001", Message.role == "user"
        )
    )
    user_messages = result.scalars().all()
    assert len(user_messages) == 2
    assert {m.id for m in user_messages} == {duplicate_id, second.id}
