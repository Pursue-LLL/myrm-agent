"""DB integration tests for InterruptedTurnMarker lifecycle.

Uses real SQLite via get_session_factory() — no mocking DB layer.
Validates:
1. Marker CRUD: insert, unique constraint, delete
2. Prune logic: stale (>freshness) and exhausted (>=max_attempts) markers removed
3. Marker survives normal insert/select lifecycle
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import delete, func, select

from app.database.models.chat import Chat, InterruptedTurnMarker
from app.platform_utils import get_session_factory


@pytest.fixture
async def session_factory():
    return get_session_factory()


@pytest.fixture
async def test_chat(session_factory):
    chat_id = f"test-autocont-{uuid.uuid4().hex[:8]}"
    async with session_factory() as db:
        db.add(Chat(id=chat_id, title="Auto-Continue DB Test"))
        await db.commit()
    yield chat_id
    async with session_factory() as db:
        await db.execute(delete(InterruptedTurnMarker).where(InterruptedTurnMarker.chat_id == chat_id))
        await db.execute(delete(Chat).where(Chat.id == chat_id))
        await db.commit()


@pytest.mark.asyncio
async def test_marker_insert_and_select(session_factory, test_chat):
    marker_id = str(uuid.uuid4())
    async with session_factory() as db:
        db.add(
            InterruptedTurnMarker(
                id=marker_id,
                chat_id=test_chat,
                user_message_id="msg-001",
                action_mode="fast",
                serialized_params={"query": "hello", "model_cfg": {"provider": "test"}},
            )
        )
        await db.commit()

    async with session_factory() as db:
        result = await db.execute(select(InterruptedTurnMarker).where(InterruptedTurnMarker.chat_id == test_chat))
        marker = result.scalar_one()

    assert marker.id == marker_id
    assert marker.chat_id == test_chat
    assert marker.attempt_count == 0
    assert marker.serialized_params["query"] == "hello"


@pytest.mark.asyncio
async def test_marker_unique_chat_id(session_factory, test_chat):
    """Only one marker per chat_id (unique constraint)."""
    async with session_factory() as db:
        db.add(
            InterruptedTurnMarker(
                id=str(uuid.uuid4()),
                chat_id=test_chat,
                user_message_id="msg-001",
                action_mode="fast",
            )
        )
        await db.commit()

    async with session_factory() as db:
        await db.execute(delete(InterruptedTurnMarker).where(InterruptedTurnMarker.chat_id == test_chat))
        db.add(
            InterruptedTurnMarker(
                id=str(uuid.uuid4()),
                chat_id=test_chat,
                user_message_id="msg-002",
                action_mode="deep",
            )
        )
        await db.commit()

    async with session_factory() as db:
        result = await db.execute(
            select(func.count()).select_from(InterruptedTurnMarker).where(InterruptedTurnMarker.chat_id == test_chat)
        )
        count = result.scalar()

    assert count == 1


@pytest.mark.asyncio
async def test_marker_delete_on_completion(session_factory, test_chat):
    """Marker should be deletable after stream completes."""
    async with session_factory() as db:
        db.add(
            InterruptedTurnMarker(
                id=str(uuid.uuid4()),
                chat_id=test_chat,
                user_message_id="msg-001",
                action_mode="fast",
            )
        )
        await db.commit()

    async with session_factory() as db:
        await db.execute(delete(InterruptedTurnMarker).where(InterruptedTurnMarker.chat_id == test_chat))
        await db.commit()

    async with session_factory() as db:
        result = await db.execute(
            select(func.count()).select_from(InterruptedTurnMarker).where(InterruptedTurnMarker.chat_id == test_chat)
        )
        assert result.scalar() == 0


@pytest.mark.asyncio
async def test_prune_stale_markers(session_factory, test_chat):
    """Markers older than freshness window should be pruned."""
    from app.lifecycle.auto_continue import _AUTO_CONTINUE_FRESHNESS_MINUTES

    stale_time = datetime.now(UTC) - timedelta(minutes=_AUTO_CONTINUE_FRESHNESS_MINUTES + 5)
    marker_id = str(uuid.uuid4())

    async with session_factory() as db:
        marker = InterruptedTurnMarker(
            id=marker_id,
            chat_id=test_chat,
            user_message_id="msg-stale",
            action_mode="fast",
        )
        db.add(marker)
        await db.commit()
        await db.execute(
            InterruptedTurnMarker.__table__.update().where(InterruptedTurnMarker.id == marker_id).values(created_at=stale_time)
        )
        await db.commit()

    cutoff = datetime.now(UTC) - timedelta(minutes=_AUTO_CONTINUE_FRESHNESS_MINUTES)
    async with session_factory() as db:
        await db.execute(delete(InterruptedTurnMarker).where(InterruptedTurnMarker.created_at < cutoff))
        await db.commit()

    async with session_factory() as db:
        result = await db.execute(
            select(func.count()).select_from(InterruptedTurnMarker).where(InterruptedTurnMarker.id == marker_id)
        )
        assert result.scalar() == 0


@pytest.mark.asyncio
async def test_prune_exhausted_markers(session_factory, test_chat):
    """Markers with attempt_count >= max should be pruned."""
    from app.lifecycle.auto_continue import _AUTO_CONTINUE_MAX_ATTEMPTS

    marker_id = str(uuid.uuid4())
    async with session_factory() as db:
        db.add(
            InterruptedTurnMarker(
                id=marker_id,
                chat_id=test_chat,
                user_message_id="msg-exhaust",
                action_mode="fast",
                attempt_count=_AUTO_CONTINUE_MAX_ATTEMPTS,
            )
        )
        await db.commit()

    async with session_factory() as db:
        await db.execute(delete(InterruptedTurnMarker).where(InterruptedTurnMarker.attempt_count >= _AUTO_CONTINUE_MAX_ATTEMPTS))
        await db.commit()

    async with session_factory() as db:
        result = await db.execute(
            select(func.count()).select_from(InterruptedTurnMarker).where(InterruptedTurnMarker.id == marker_id)
        )
        assert result.scalar() == 0


@pytest.mark.asyncio
async def test_cascade_delete_on_chat_removal(session_factory, test_chat):
    """Marker should be cascade-deleted when parent chat is removed."""
    async with session_factory() as db:
        db.add(
            InterruptedTurnMarker(
                id=str(uuid.uuid4()),
                chat_id=test_chat,
                user_message_id="msg-cascade",
                action_mode="fast",
            )
        )
        await db.commit()

    async with session_factory() as db:
        await db.execute(delete(Chat).where(Chat.id == test_chat))
        await db.commit()

    async with session_factory() as db:
        result = await db.execute(
            select(func.count()).select_from(InterruptedTurnMarker).where(InterruptedTurnMarker.chat_id == test_chat)
        )
        assert result.scalar() == 0


@pytest.mark.asyncio
async def test_attempt_count_increment(session_factory, test_chat):
    """attempt_count should be updatable (simulating crash-loop breaker)."""
    marker_id = str(uuid.uuid4())
    async with session_factory() as db:
        db.add(
            InterruptedTurnMarker(
                id=marker_id,
                chat_id=test_chat,
                user_message_id="msg-retry",
                action_mode="fast",
                attempt_count=0,
            )
        )
        await db.commit()

    async with session_factory() as db:
        await db.execute(
            InterruptedTurnMarker.__table__.update()
            .where(InterruptedTurnMarker.id == marker_id)
            .values(attempt_count=InterruptedTurnMarker.attempt_count + 1)
        )
        await db.commit()

    async with session_factory() as db:
        result = await db.execute(select(InterruptedTurnMarker).where(InterruptedTurnMarker.id == marker_id))
        marker = result.scalar_one()

    assert marker.attempt_count == 1


@pytest.mark.asyncio
async def test_serialized_params_json_roundtrip(session_factory, test_chat):
    """serialized_params JSON should survive insert/select roundtrip intact."""
    marker_id = str(uuid.uuid4())
    params = {
        "query": "hello world",
        "model_cfg": {"provider": "openai", "model": "gpt-4o"},
        "action_mode": "fast",
        "agent_id": "default",
        "tags": ["auto_continue"],
        "nested": {"a": [1, 2, 3], "b": None},
    }
    async with session_factory() as db:
        db.add(
            InterruptedTurnMarker(
                id=marker_id,
                chat_id=test_chat,
                user_message_id="msg-json",
                action_mode="fast",
                serialized_params=params,
            )
        )
        await db.commit()

    async with session_factory() as db:
        result = await db.execute(select(InterruptedTurnMarker).where(InterruptedTurnMarker.id == marker_id))
        marker = result.scalar_one()

    assert marker.serialized_params == params
    assert marker.serialized_params["nested"]["b"] is None
    assert marker.serialized_params["nested"]["a"] == [1, 2, 3]


@pytest.mark.asyncio
async def test_fresh_marker_survives_prune(session_factory, test_chat):
    """A marker within freshness window should NOT be pruned."""
    from app.lifecycle.auto_continue import _AUTO_CONTINUE_FRESHNESS_MINUTES

    marker_id = str(uuid.uuid4())
    async with session_factory() as db:
        db.add(
            InterruptedTurnMarker(
                id=marker_id,
                chat_id=test_chat,
                user_message_id="msg-fresh",
                action_mode="fast",
                attempt_count=0,
            )
        )
        await db.commit()

    cutoff = datetime.now(UTC) - timedelta(minutes=_AUTO_CONTINUE_FRESHNESS_MINUTES)
    async with session_factory() as db:
        await db.execute(delete(InterruptedTurnMarker).where(InterruptedTurnMarker.created_at < cutoff))
        await db.commit()

    async with session_factory() as db:
        result = await db.execute(
            select(func.count()).select_from(InterruptedTurnMarker).where(InterruptedTurnMarker.id == marker_id)
        )
        assert result.scalar() == 1, "Fresh marker should survive prune"


@pytest.mark.asyncio
async def test_write_marker_function_creates_and_replaces(session_factory, test_chat):
    """_write_interrupted_turn_marker should create a new marker and replace existing one."""

    from app.services.agent.stream_session.orchestrator import _write_interrupted_turn_marker

    request = MagicMock()
    request.chat_id = test_chat
    request.message_id = "msg-write-001"
    request.action_mode = "fast"
    request.agent_id = "test-agent"

    params = MagicMock()
    params.model_dump.return_value = {"query": "test write", "model_cfg": {"provider": "test"}}

    with patch("app.platform_utils.get_session_factory", return_value=session_factory):
        await _write_interrupted_turn_marker(request, params)

    async with session_factory() as db:
        result = await db.execute(select(InterruptedTurnMarker).where(InterruptedTurnMarker.chat_id == test_chat))
        marker = result.scalar_one()

    assert marker.user_message_id == "msg-write-001"
    assert marker.action_mode == "fast"
    assert marker.serialized_params["query"] == "test write"

    request.message_id = "msg-write-002"
    params.model_dump.return_value = {"query": "second write", "model_cfg": {"provider": "test"}}

    with patch("app.platform_utils.get_session_factory", return_value=session_factory):
        await _write_interrupted_turn_marker(request, params)

    async with session_factory() as db:
        result = await db.execute(select(InterruptedTurnMarker).where(InterruptedTurnMarker.chat_id == test_chat))
        marker = result.scalar_one()

    assert marker.user_message_id == "msg-write-002", "Second write should replace first"
    assert marker.serialized_params["query"] == "second write"


@pytest.mark.asyncio
async def test_clear_marker_function(session_factory, test_chat):
    """_clear_interrupted_turn_marker should remove marker for given chat_id."""
    from app.services.agent.stream_session.stream_finalize import _clear_interrupted_turn_marker

    async with session_factory() as db:
        db.add(
            InterruptedTurnMarker(
                id=str(uuid.uuid4()),
                chat_id=test_chat,
                user_message_id="msg-clear",
                action_mode="fast",
            )
        )
        await db.commit()

    with patch("app.platform_utils.get_session_factory", return_value=session_factory):
        await _clear_interrupted_turn_marker(test_chat)

    async with session_factory() as db:
        result = await db.execute(
            select(func.count()).select_from(InterruptedTurnMarker).where(InterruptedTurnMarker.chat_id == test_chat)
        )
        assert result.scalar() == 0
