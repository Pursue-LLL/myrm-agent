"""Tests for BehavioralMeasurementService."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.api import BehavioralStatsOptions
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.channel_message import ChannelMessageModel
from app.database.models.chat import Message
from app.services.memory.behavioral.measurement_service import (
    BehavioralMeasurementService,
)


@pytest.mark.asyncio
async def test_collect_behavioral_messages_filters_bot_and_sorts() -> None:
    db = AsyncMock(spec=AsyncSession)
    manager = MagicMock()

    base_time = datetime(2026, 9, 4, 12, 0, 0, tzinfo=UTC)

    # Mock Channel messages
    c1 = ChannelMessageModel(
        id="c1",
        channel="slack",
        chat_id="general",
        sender_id="bot_alert",
        sender_name="Prometheus AlertBot",  # should be filtered
        content="CPU high",
        is_self=False,
        learning_eligible=True,
        created_at=base_time,
    )
    c2 = ChannelMessageModel(
        id="c2",
        channel="slack",
        chat_id="general",
        sender_id="colleague_1",
        sender_name="Alice",
        content="Good morning team",
        is_self=False,
        learning_eligible=True,
        created_at=base_time + timedelta(seconds=10),
    )
    c3 = ChannelMessageModel(
        id="c3",
        channel="slack",
        chat_id="general",
        sender_id="user_me",
        sender_name="Me",
        content="Morning Alice!",
        is_self=True,
        learning_eligible=True,
        created_at=base_time + timedelta(seconds=30),
    )

    # Mock WebUI chat message
    m1 = Message(
        id="m1",
        chat_id="chat_123",
        role="user",
        content="Refactor the authentication module",
        created_at=base_time + timedelta(seconds=60),
        is_active=True,
        sent_at=base_time + timedelta(seconds=60),
        sent_timezone="UTC",
    )

    # Mock execute results
    channel_exec_result = MagicMock()
    channel_exec_result.scalars.return_value.all.return_value = [c1, c2, c3]

    chat_exec_result = MagicMock()
    chat_exec_result.scalars.return_value.all.return_value = [m1]

    db.execute.side_effect = [channel_exec_result, chat_exec_result]

    service = BehavioralMeasurementService(db, manager)
    messages = await service.collect_behavioral_messages(lookback_days=7)

    # c1 (Prometheus AlertBot) filtered out, remaining c2, c3, m1
    assert len(messages) == 3
    assert messages[0].id == "channel:c2"
    assert messages[1].id == "channel:c3"
    assert messages[2].id == "chat:m1"

    # Verify self flags
    assert not messages[0].is_self
    assert messages[1].is_self
    assert messages[2].is_self


@pytest.mark.asyncio
async def test_sync_profile_attributes_persists_when_thresholds_met() -> None:
    db = AsyncMock(spec=AsyncSession)
    manager = MagicMock()
    manager.set_system_profile_attribute = AsyncMock()

    base_time = datetime(2026, 9, 4, 10, 0, 0, tzinfo=UTC)

    # Generate 25 turns to satisfy thresholds (min_self_messages=20, min_latency_samples=10)
    channel_rows: list[ChannelMessageModel] = []
    for i in range(25):
        channel_rows.append(
            ChannelMessageModel(
                id=f"other_{i}",
                channel="feishu",
                chat_id="chat_dev",
                sender_id="dev_colleague",
                sender_name="David",
                content=f"Ping {i}",
                is_self=False,
                learning_eligible=True,
                created_at=base_time + timedelta(minutes=i * 2),
            )
        )
        channel_rows.append(
            ChannelMessageModel(
                id=f"self_{i}",
                channel="feishu",
                chat_id="chat_dev",
                sender_id="me",
                sender_name="Myself",
                content=f"Pong {i}",
                is_self=True,
                learning_eligible=True,
                created_at=base_time + timedelta(minutes=i * 2, seconds=15),
            )
        )

    channel_exec_result = MagicMock()
    channel_exec_result.scalars.return_value.all.return_value = channel_rows

    chat_exec_result = MagicMock()
    chat_exec_result.scalars.return_value.all.return_value = []

    db.execute.side_effect = [channel_exec_result, chat_exec_result]

    service = BehavioralMeasurementService(db, manager)
    options = BehavioralStatsOptions(min_self_messages=20, min_latency_samples=10)
    updated_keys = await service.sync_profile_attributes(options=options)

    assert "routine_active_hours" in updated_keys
    assert "routine_reply_latency" in updated_keys
    assert "routine_top_collaborators" in updated_keys
    assert manager.set_system_profile_attribute.call_count == 3
