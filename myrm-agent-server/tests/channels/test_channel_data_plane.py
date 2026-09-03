"""Unit tests for Channel Data Plane (models, repository, and service).

Covers:
- is_learning_eligible heuristic filtering
- ChannelMessageRepository CRUD, ordering, filtering, and rolling 30-day purge
- ChannelDataPlaneService inbound recording, redaction, and outbound reply persistence
- ContextEntry reconstruction
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.channels.routing.channel_data_plane import (
    ChannelDataPlaneService,
    is_learning_eligible,
)
from app.channels.types import InboundMessage
from app.database.models.base import Base
from app.database.models.channel_message import ChannelMessageModel
from app.database.repositories.channel_message_repo import ChannelMessageRepository


@pytest.fixture
async def async_db() -> AsyncGenerator[AsyncSession, None]:
    """In-memory SQLite async database session for isolated repository testing."""
    engine: AsyncEngine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as session:
        yield session

    await engine.dispose()


class TestLearningEligibility:
    """Tests for the is_learning_eligible noise rejection heuristics."""

    def test_eligible_normal_text(self) -> None:
        assert is_learning_eligible("Team, please review the latest API spec before release.") is True
        assert is_learning_eligible("Can we deploy to staging at 3pm?", sender_name="Alice") is True

    def test_ineligible_slash_commands(self) -> None:
        assert is_learning_eligible("/help") is False
        assert is_learning_eligible("/clear context") is False
        assert is_learning_eligible("!deploy prod") is False
        assert is_learning_eligible("#status") is False

    def test_ineligible_empty_or_trivial(self) -> None:
        assert is_learning_eligible("") is False
        assert is_learning_eligible("   ") is False
        assert is_learning_eligible("k") is False
        assert is_learning_eligible("?") is False

    def test_ineligible_bot_senders(self) -> None:
        assert is_learning_eligible("Pipeline failed on main", sender_name="CI/CD Bot") is False
        assert is_learning_eligible("CPU usage > 90%", sender_name="Prometheus-AlertManager") is False
        assert is_learning_eligible("NullPointerException", sender_name="Sentry") is False
        assert is_learning_eligible("今日打卡已完成", sender_name="打卡机器人") is False
        assert is_learning_eligible("定时健康检查正常", sender_name="运维提醒助手") is False

    def test_eligible_sender_with_substring(self) -> None:
        assert is_learning_eligible("Let's proceed with design.", sender_name="Abbott") is True


class TestChannelMessageRepository:
    """Direct database repository operations test suite."""

    @pytest.mark.asyncio
    async def test_record_and_get_recent_context(self, async_db: AsyncSession) -> None:
        now = datetime.now(timezone.utc)
        m1 = ChannelMessageModel(
            id="msg_001",
            channel="feishu",
            chat_id="chat_alpha",
            sender_id="user_1",
            content="Message 1",
            is_trigger=False,
            is_self=False,
            created_at=now - timedelta(minutes=5),
        )
        m2 = ChannelMessageModel(
            id="msg_002",
            channel="feishu",
            chat_id="chat_alpha",
            sender_id="user_2",
            content="Message 2",
            is_trigger=True,
            is_self=False,
            created_at=now - timedelta(minutes=2),
        )
        m3 = ChannelMessageModel(
            id="msg_003",
            channel="feishu",
            chat_id="chat_other",
            sender_id="user_3",
            content="Irrelevant group message",
            is_trigger=False,
            is_self=False,
            created_at=now,
        )

        await ChannelMessageRepository.record_message(async_db, m1)
        await ChannelMessageRepository.record_message(async_db, m2)
        await ChannelMessageRepository.record_message(async_db, m3)
        await async_db.commit()

        context = await ChannelMessageRepository.get_recent_context(
            async_db, channel="feishu", chat_id="chat_alpha", limit=10
        )
        assert len(context) == 2
        # Chronological order: oldest first
        assert context[0].id == "msg_001"
        assert context[1].id == "msg_002"

    @pytest.mark.asyncio
    async def test_get_learning_candidates_filtering(self, async_db: AsyncSession) -> None:
        now = datetime.now(timezone.utc)
        # 1. Eligible user message
        m1 = ChannelMessageModel(
            id="cand_1",
            channel="slack",
            chat_id="chan_1",
            sender_id="u1",
            content="High value decision rationale",
            learning_eligible=True,
            is_self=False,
            created_at=now - timedelta(hours=1),
        )
        # 2. Ineligible noise
        m2 = ChannelMessageModel(
            id="cand_2",
            channel="slack",
            chat_id="chan_1",
            sender_id="u2",
            content="/skip",
            learning_eligible=False,
            is_self=False,
            created_at=now - timedelta(minutes=30),
        )
        # 3. Agent's own message (must never be ingested into human profile memory)
        m3 = ChannelMessageModel(
            id="cand_3",
            channel="slack",
            chat_id="chan_1",
            sender_id="agent",
            content="Understood, executing task.",
            learning_eligible=True,
            is_self=True,
            created_at=now - timedelta(minutes=10),
        )

        for m in (m1, m2, m3):
            await ChannelMessageRepository.record_message(async_db, m)
        await async_db.commit()

        candidates = await ChannelMessageRepository.get_learning_candidates(async_db, channel="slack")
        assert len(candidates) == 1
        assert candidates[0].id == "cand_1"

    @pytest.mark.asyncio
    async def test_prune_expired_messages(self, async_db: AsyncSession) -> None:
        now = datetime.now(timezone.utc)
        # 40 days old (should be purged)
        old_msg = ChannelMessageModel(
            id="old_01",
            channel="dingtalk",
            chat_id="dt_chat",
            sender_id="user_old",
            content="Old topic from last month",
            created_at=now - timedelta(days=40),
        )
        # 10 days old (should be retained)
        recent_msg = ChannelMessageModel(
            id="recent_01",
            channel="dingtalk",
            chat_id="dt_chat",
            sender_id="user_recent",
            content="Recent discussions",
            created_at=now - timedelta(days=10),
        )

        await ChannelMessageRepository.record_message(async_db, old_msg)
        await ChannelMessageRepository.record_message(async_db, recent_msg)
        await async_db.commit()

        purged_count = await ChannelMessageRepository.prune_expired(async_db, retention_days=30)
        await async_db.commit()

        assert purged_count == 1
        remaining = await ChannelMessageRepository.get_recent_context(
            async_db, channel="dingtalk", chat_id="dt_chat"
        )
        assert len(remaining) == 1
        assert remaining[0].id == "recent_01"

    @pytest.mark.asyncio
    async def test_get_channel_stats_and_clear_history(self, async_db: AsyncSession) -> None:
        m1 = ChannelMessageModel(
            id="cnt_1",
            channel="wecom",
            chat_id="w1",
            sender_id="u1",
            content="One",
            learning_eligible=True,
            is_trigger=True,
            created_at=datetime.now(timezone.utc),
        )
        m2 = ChannelMessageModel(
            id="cnt_2",
            channel="lark",
            chat_id="l1",
            sender_id="u2",
            content="Two",
            learning_eligible=False,
            is_trigger=False,
            created_at=datetime.now(timezone.utc),
        )
        await ChannelMessageRepository.record_message(async_db, m1)
        await ChannelMessageRepository.record_message(async_db, m2)
        await async_db.commit()

        stats_all = await ChannelMessageRepository.get_channel_stats(async_db)
        assert stats_all["total_messages"] == 2
        assert stats_all["learning_eligible"] == 1
        assert stats_all["trigger_messages"] == 1

        stats_wecom = await ChannelMessageRepository.get_channel_stats(async_db, channel="wecom")
        assert stats_wecom["total_messages"] == 1
        assert stats_wecom["learning_eligible"] == 1

        stats_unknown = await ChannelMessageRepository.get_channel_stats(async_db, channel="unknown")
        assert stats_unknown["total_messages"] == 0

        # Test clear_chat_history
        cleared = await ChannelMessageRepository.clear_chat_history(async_db, channel="wecom", chat_id="w1")
        await async_db.commit()
        assert cleared == 1

        stats_after = await ChannelMessageRepository.get_channel_stats(async_db, channel="wecom")
        assert stats_after["total_messages"] == 0


class TestChannelDataPlaneService:
    """Service layer testing including security redaction and error resilience."""

    @pytest.mark.asyncio
    async def test_record_inbound_redacts_credentials(self) -> None:
        msg = InboundMessage(
            channel="feishu",
            sender_id="user_x",
            sender_name="Bob",
            chat_id="chat_secret",
            content="Here is the test key: sk-live-1234567890abcdef12345678",
            message_id="msg_redact_test",
        )

        with patch("app.channels.routing.channel_data_plane.get_session") as mock_get_session:
            mock_session = AsyncMock()
            mock_get_session.return_value.__aenter__.return_value = mock_session

            entry = await ChannelDataPlaneService.record_inbound(msg, is_trigger=True)
            assert entry is not None
            assert entry.is_trigger is True
            assert entry.is_self is False
            # Secret must be replaced with sanitized placeholder
            assert "sk-live-1234567890abcdef12345678" not in entry.content
            assert "sk-***" in entry.content or "[REDACTED" in entry.content or "*" in entry.content

    @pytest.mark.asyncio
    async def test_record_inbound_missing_chat_id_safely_ignored(self) -> None:
        msg = InboundMessage(
            channel="telegram",
            sender_id="",
            chat_id="",
            content="Hello",
        )
        entry = await ChannelDataPlaneService.record_inbound(msg, is_trigger=False)
        assert entry is None

    @pytest.mark.asyncio
    async def test_record_outbound_persists_agent_reply(self) -> None:
        with patch("app.channels.routing.channel_data_plane.get_session") as mock_get_session:
            mock_session = AsyncMock()
            mock_get_session.return_value.__aenter__.return_value = mock_session

            entry = await ChannelDataPlaneService.record_outbound(
                channel="slack",
                chat_id="group_1",
                content="Task completed successfully.",
                reply_to_id="user_msg_10",
            )
            assert entry is not None
            assert entry.is_self is True
            assert entry.learning_eligible is False
            assert entry.sender_id == "agent"

    @pytest.mark.asyncio
    async def test_get_recent_context_entries_failure_returns_empty_list(self) -> None:
        with patch("app.channels.routing.channel_data_plane.get_session", side_effect=RuntimeError("DB disconnected")):
            entries = await ChannelDataPlaneService.get_recent_context_entries("slack", "chan_1")
            assert entries == []
