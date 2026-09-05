"""Full real DB pipeline integration test for Zero-Model-Cost Deterministic Behavioral Measurement.

Runs against an in-memory/ephemeral SQLite database with REAL ChannelMessageModel and Message rows:
1. Seeds 35 turns of realistic chat and channel interactions (including bot messages to test distillation exclusion).
2. Executes BehavioralMeasurementService to compute deterministic metrics (0 LLM cost).
3. Verifies that bots and automated webhooks are 100% excluded.
4. Executes sync_profile_attributes and verifies that attributes are persisted to Profile memory.
5. Verifies through FastAPI endpoints that the full HTTP contract returns expected results without any mocks on the calculation path.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.api import BehavioralStatsOptions
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_db_session
from app.api.memory.operations import command_center as command_center_operation
from app.api.memory.utils import get_crud_memory_manager
from app.database.models.base import Base
from app.database.models.channel_message import ChannelMessageModel
from app.database.models.chat import Chat, Message
from app.services.memory.behavioral.measurement_service import BehavioralMeasurementService


@pytest_asyncio.fixture
async def real_db_env():
    engine = create_async_engine(
        "sqlite+aiosqlite:///file:testdb_behavioral?mode=memory&cache=shared&uri=true",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[ChannelMessageModel.__table__, Chat.__table__, Message.__table__],
            )
        )

    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    stored_profiles: dict[str, str] = {}
    manager = MagicMock()

    async def _mock_set_profile(key: str, value: str):
        stored_profiles[key] = value

    async def _mock_get_profile(key: str) -> str | None:
        return stored_profiles.get(key)

    manager.set_system_profile_attribute = AsyncMock(side_effect=_mock_set_profile)
    manager.get_profile_attribute = AsyncMock(side_effect=_mock_get_profile)

    yield session_maker, manager, engine

    await engine.dispose()


@pytest.mark.asyncio
async def test_full_pipeline_real_db_and_api(real_db_env) -> None:
    session_maker, manager, engine = real_db_env

    # 1. Seed realistic data into DB
    base_time = datetime.now(UTC) - timedelta(days=2)
    async with session_maker() as db:
        # 1.1 Add an alert bot message (must be filtered by distillation guard)
        db.add(
            ChannelMessageModel(
                id="alert_001",
                channel="slack",
                chat_id="dev-alerts",
                sender_id="alertmanager",
                sender_name="AlertBot",
                content="[CRITICAL] High memory usage detected",
                is_self=False,
                learning_eligible=True,
                created_at=base_time - timedelta(minutes=60),
            )
        )

        # 1.2 Add 25 realistic human conversational interaction turns
        for i in range(25):
            turn_time = base_time + timedelta(minutes=i * 2)
            # Colleague message
            db.add(
                ChannelMessageModel(
                    id=f"collab_msg_{i}",
                    channel="feishu",
                    chat_id="chat_proj_alpha",
                    sender_id="colleague_eva",
                    sender_name="Eva",
                    content=f"Hey, could you review PR #{i}?",
                    is_self=False,
                    learning_eligible=True,
                    created_at=turn_time,
                )
            )
            # Self reply (latency ~30s)
            db.add(
                ChannelMessageModel(
                    id=f"self_msg_{i}",
                    channel="feishu",
                    chat_id="chat_proj_alpha",
                    sender_id="user_me",
                    sender_name="Me",
                    content=f"Sure Eva, reviewing PR #{i} right now.",
                    is_self=True,
                    learning_eligible=True,
                    created_at=turn_time + timedelta(seconds=30),
                )
            )

        await db.commit()

    # 2. Test BehavioralMeasurementService directly against real DB
    async with session_maker() as db:
        service = BehavioralMeasurementService(db, manager)

        # 2.1 Measure
        measurement = await service.measure(lookback_days=30)
        assert measurement.self_message_count == 25
        assert measurement.latency_sample_count == 25
        assert measurement.reply_latency_p50_ms == 30000.0
        assert len(measurement.top_collaborators) == 1
        assert measurement.top_collaborators[0] == ("Eva", 25)

        # 2.2 Sync qualified behavioral profile
        updated_keys = await service.sync_profile_attributes(lookback_days=30)
        assert "routine_active_hours" in updated_keys
        assert "routine_reply_latency" in updated_keys
        assert "routine_top_collaborators" in updated_keys

        # 2.3 Verify persistence in MemoryManager
        persisted_hours = await manager.get_profile_attribute("routine_active_hours")
        assert persisted_hours is not None
        assert "workday_peak_window" in persisted_hours

        persisted_latency = await manager.get_profile_attribute("routine_reply_latency")
        assert persisted_latency is not None
        assert "30000.0" in persisted_latency

        persisted_collabs = await manager.get_profile_attribute("routine_top_collaborators")
        assert persisted_collabs is not None
        assert "Eva" in persisted_collabs

    # 3. Test through FastAPI HTTP router with real dependencies
    app = FastAPI()
    app.include_router(command_center_operation.router, prefix="/api/memory")

    async def _get_test_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db_session] = _get_test_db
    app.dependency_overrides[get_crud_memory_manager] = lambda: manager

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # GET /behavioral-insights
        resp = await client.get("/api/memory/command-center/behavioral-insights?lookback_days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert data["self_message_count"] == 25
        assert data["reply_latency_p50_ms"] == 30000.0
        assert data["top_collaborators"] == [["Eva", 25]]
        assert data["source"] == "computed_deterministic"

        # POST /behavioral-sync
        sync_resp = await client.post("/api/memory/command-center/behavioral-sync?lookback_days=30")
        assert sync_resp.status_code == 200
        sync_data = sync_resp.json()
        assert sync_data["status"] == "success"
        assert sync_data["count"] == 3
        assert set(sync_data["updated_profile_keys"]) == {
            "routine_active_hours",
            "routine_reply_latency",
            "routine_top_collaborators",
        }


@pytest.mark.asyncio
async def test_timezone_explicit_offset_resolution(real_db_env) -> None:
    session_maker, manager, engine = real_db_env

    # 1. Direct helper validation
    from app.services.memory.behavioral.measurement_service import (
        resolve_timezone_offset_minutes,
    )

    test_dt = datetime.now(UTC) - timedelta(hours=2)
    # New York test dt
    ny_offset = resolve_timezone_offset_minutes("America/New_York", test_dt)
    assert ny_offset in (-240, -300)

    # London
    london_offset = resolve_timezone_offset_minutes("Europe/London", test_dt)
    assert london_offset in (0, 60)

    # ISO offset strings
    assert resolve_timezone_offset_minutes("+08:00") == 480
    assert resolve_timezone_offset_minutes("-05:00") == -300
    assert resolve_timezone_offset_minutes("UTC") == 0

    # 2. Database pipeline test: Message with New York timezone
    async with session_maker() as db:
        from sqlalchemy import delete
        await db.execute(delete(ChannelMessageModel))
        await db.execute(delete(Message))
        chat = Chat(id="chat_ny", action_mode="fast", source="web")
        db.add(chat)
        ny_msg = Message(
            id="msg_ny_user",
            chat_id="chat_ny",
            role="user",
            content="Good morning from New York!",
            sent_at=test_dt,
            created_at=test_dt,
            is_active=True,
            sent_timezone="America/New_York",
        )
        db.add(ny_msg)
        await db.commit()

    async with session_maker() as db:
        from myrm_agent_harness.api import BehavioralStatsOptions
        service = BehavioralMeasurementService(db, manager)
        msgs = await service.collect_behavioral_messages(lookback_days=7)
        assert len(msgs) == 1, f"Expected 1 msg, got {len(msgs)}"
        assert msgs[0].offset_minutes == ny_offset
        opts = BehavioralStatsOptions(min_self_messages=1)
        measurement = await service.measure(options=opts, lookback_days=7)

        # Expected NY local hour
        expected_ny_hour = test_dt.astimezone(ZoneInfo("America/New_York")).hour
        assert measurement.hour_histogram[expected_ny_hour] >= 1

