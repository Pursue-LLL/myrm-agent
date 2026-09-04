"""Unit tests for BehavioralMeasurementService."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
import json
from pathlib import Path
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models.base import Base
from app.database.models.channel_message import ChannelMessageModel
from app.database.models.memory import ProfileAttribute
from app.services.memory.behavioral_service import BehavioralMeasurementService


@pytest_asyncio.fixture
async def db_session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    db_file = tmp_path / f"test_{uuid.uuid4().hex[:8]}.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_measure_and_sync_profile_success(db_session: AsyncSession) -> None:
    base_time = datetime(2026, 9, 4, 6, 0, 0, tzinfo=UTC)

    # Insert 25 turns to satisfy thresholds (min_self_messages=20, min_latency_samples=10)
    for i in range(25):
        # Peer message
        db_session.add(
            ChannelMessageModel(
                id=f"peer_{i}",
                channel="feishu",
                chat_id="chat_1",
                sender_id="colleague",
                sender_name="Colleague",
                content=f"Question {i}",
                is_self=False,
                is_group=True,
                learning_eligible=True,
                created_at=datetime.fromtimestamp(base_time.timestamp() + i * 120, tz=UTC),
            )
        )
        # Self response (20s later)
        db_session.add(
            ChannelMessageModel(
                id=f"self_{i}",
                channel="feishu",
                chat_id="chat_1",
                sender_id="user_me",
                sender_name="Me",
                content=f"Answer {i}",
                is_self=True,
                is_group=True,
                learning_eligible=True,
                created_at=datetime.fromtimestamp(base_time.timestamp() + i * 120 + 20, tz=UTC),
            )
        )
    await db_session.flush()

    measurement = await BehavioralMeasurementService.measure_and_sync_profile(
        db_session,
        offset_minutes=480,
    )

    assert measurement.self_message_count == 25
    assert measurement.latency_sample_count == 25
    assert measurement.channel_distribution == {"feishu": 25}

    # Verify insights API reads back the calculated data
    insights = await BehavioralMeasurementService.get_current_insights(
        db_session,
        offset_minutes=480,
    )
    assert insights["source"] == "persisted"
    assert insights["self_message_count"] == 25
    assert insights["reply_latency_p50_ms"] == 20000.0


@pytest.mark.asyncio
async def test_user_override_wins_against_deterministic_stat(db_session: AsyncSession) -> None:
    # Pre-populate a user-curated manual profile attribute
    user_override = ProfileAttribute(
        id=str(uuid.uuid4()),
        attribute_key="routine_active_hours",
        attribute_value=json.dumps({"manual_preference": "I work at night"}),
        category="routine",
        confidence=1.0,
        source="user",
    )
    db_session.add(user_override)
    await db_session.flush()

    # Now run deterministic measurement with enough data
    base_time = datetime(2026, 9, 4, 6, 0, 0, tzinfo=UTC)
    for i in range(25):
        db_session.add(
            ChannelMessageModel(
                id=f"self_turn_{i}",
                channel="webui",
                chat_id="c1",
                sender_id="me",
                content=f"Self message {i}",
                is_self=True,
                learning_eligible=True,
                created_at=datetime.fromtimestamp(base_time.timestamp() + i * 10, tz=UTC),
            )
        )
    await db_session.flush()

    await BehavioralMeasurementService.measure_and_sync_profile(
        db_session,
        offset_minutes=480,
    )

    # Re-fetch the attribute
    refreshed = await db_session.get(ProfileAttribute, user_override.id)
    assert refreshed is not None
    assert refreshed.source == "user"
    assert "manual_preference" in refreshed.attribute_value
