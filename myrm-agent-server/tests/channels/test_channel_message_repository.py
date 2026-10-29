"""Unit tests for ChannelMessageRepository: recent-context ordering, learning-candidate filtering, the rolling
30-day purge, per-channel stats and history clearing, and idempotent duplicate writes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.channel_message import ChannelMessageModel
from app.database.repositories.channel_message_repo import ChannelMessageRepository


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

        context = await ChannelMessageRepository.get_recent_context(async_db, channel="feishu", chat_id="chat_alpha", limit=10)
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
        remaining = await ChannelMessageRepository.get_recent_context(async_db, channel="dingtalk", chat_id="dt_chat")
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

    @pytest.mark.asyncio
    async def test_record_message_idempotent_duplicate_absorbed(self, async_db: AsyncSession) -> None:
        """Webhook duplicate retry delivery must be idempotently absorbed without failing the transaction."""
        m1 = ChannelMessageModel(
            id="dup_msg_001",
            channel="slack",
            chat_id="chat_retry",
            sender_id="user_retry",
            content="Original delivery",
            created_at=datetime.now(timezone.utc),
        )
        # First delivery
        await ChannelMessageRepository.record_message(async_db, m1)
        await async_db.commit()

        # Second delivery with the same primary key id (simulates webhook retry)
        m2 = ChannelMessageModel(
            id="dup_msg_001",
            channel="slack",
            chat_id="chat_retry",
            sender_id="user_retry",
            content="Retry delivery payload",
            created_at=datetime.now(timezone.utc),
        )
        # Must not raise IntegrityError; cleanly absorbed via SAVEPOINT
        await ChannelMessageRepository.record_message(async_db, m2)
        await async_db.commit()

        # Verify only one row exists and session remains completely usable
        msgs = await ChannelMessageRepository.get_recent_context(async_db, channel="slack", chat_id="chat_retry")
        assert len(msgs) == 1
        assert msgs[0].id == "dup_msg_001"
