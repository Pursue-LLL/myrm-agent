"""Unit tests for EvidencePlaybackService."""

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.models.base import Base
from app.database.models.channel_message import ChannelMessageModel
from app.database.models.chat import Chat, Message
from app.services.memory.evidence.playback_service import EvidencePlaybackService


@pytest_asyncio.fixture
async def playback_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    yield session_maker
    await engine.dispose()


@pytest.mark.asyncio
async def test_evidence_playback_resolves_chat_turns_with_redaction(playback_db):
    session_maker = playback_db
    now = datetime.now(UTC)

    async with session_maker() as session:
        chat = Chat(id="chat-alpha", title="Architecture chat", source="web")
        session.add(chat)

        msg1 = Message(
            id="msg-1",
            chat_id="chat-alpha",
            role="user",
            content="Can we use secret token=sk-1234567890abcdef?",
            sent_at=now - timedelta(seconds=20),
            sent_timezone="UTC",
        )
        msg2 = Message(
            id="msg-2",
            chat_id="chat-alpha",
            role="assistant",
            content="Never hardcode secrets. Always use environment variables.",
            sent_at=now - timedelta(seconds=10),
            sent_timezone="UTC",
        )
        msg3 = Message(
            id="msg-3",
            chat_id="chat-alpha",
            role="user",
            content="Understood, I will use ENV instead.",
            sent_at=now,
            sent_timezone="UTC",
        )
        session.add_all([msg1, msg2, msg3])
        await session.commit()

    async with session_maker() as session:
        service = EvidencePlaybackService(session)
        result = await service.get_playback(
            source_id="chat-alpha",
            message_id="msg-2",
            quote_snippet="Never hardcode secrets",
        )

        assert result.status == "live_context"
        assert result.source_type == "chat"
        assert result.target_message_id == "msg-2"
        assert len(result.turns) == 3

        # Target message verification
        target_turn = [t for t in result.turns if t.is_target][0]
        assert target_turn.message_id == "msg-2"
        assert target_turn.role == "assistant"

        # Redaction verification on prior user message
        prior_turn = [t for t in result.turns if t.message_id == "msg-1"][0]
        assert "token=***REDACTED***" in prior_turn.content
        assert "sk-1234567890abcdef" not in prior_turn.content


@pytest.mark.asyncio
async def test_evidence_playback_resolves_channel_messages(playback_db):
    session_maker = playback_db
    now = datetime.now(UTC)

    async with session_maker() as session:
        cmsg1 = ChannelMessageModel(
            id="cmsg-1",
            channel="feishu",
            chat_id="oc_group_1",
            sender_id="user_alice",
            sender_name="Alice",
            content="We should standardize on Node 20 LTS.",
            is_self=False,
            created_at=now - timedelta(minutes=1),
        )
        cmsg2 = ChannelMessageModel(
            id="cmsg-2",
            channel="feishu",
            chat_id="oc_group_1",
            sender_id="user_me",
            sender_name="Me",
            content="Agreed, updating Dockerfile now.",
            is_self=True,
            created_at=now,
        )
        session.add_all([cmsg1, cmsg2])
        await session.commit()

    async with session_maker() as session:
        service = EvidencePlaybackService(session)
        result = await service.get_playback(
            channel_id="feishu",
            message_id="cmsg-1",
            quote_snippet="Node 20 LTS",
        )

        assert result.status == "live_context"
        assert result.source_type == "channel"
        assert result.channel == "feishu"
        assert len(result.turns) == 2
        assert result.turns[0].is_target is True
        assert result.turns[0].sender_name == "Alice"


@pytest.mark.asyncio
async def test_evidence_playback_fallback_for_archived_quote(playback_db):
    session_maker = playback_db
    async with session_maker() as session:
        service = EvidencePlaybackService(session)
        result = await service.get_playback(
            source_id="purged-chat",
            message_id="purged-msg",
            quote_snippet="Deprecated legacy command with password=secret123",
            author_name="DevLead",
        )

        assert result.status == "archived_snapshot"
        assert result.target_message_id == "purged-msg"
        assert len(result.turns) == 1
        assert "password=***REDACTED***" in result.quote_snippet
        assert "secret123" not in result.quote_snippet
        assert result.turns[0].sender_name == "DevLead"
