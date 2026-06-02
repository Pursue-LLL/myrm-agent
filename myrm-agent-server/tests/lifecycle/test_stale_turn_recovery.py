"""Tests for stale agent turn recovery on startup.

Verifies that _recover_stale_agent_turns() correctly marks
PENDING/RUNNING turns as INTERRUPTED during server restart.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.database.models import AgentTurn
from app.database.models.chat import Chat
from app.platform_utils import get_session_factory
from app.services.event.types import TurnStatus


@pytest.fixture
async def session_factory():
    return get_session_factory()


@pytest.fixture
async def test_chat(session_factory):
    """Create a minimal chat for turn tests."""
    chat_id = f"test-stale-recovery-{uuid.uuid4().hex[:8]}"
    async with session_factory() as db:
        chat = Chat(id=chat_id, title="Stale Recovery Test")
        db.add(chat)
        await db.commit()
    return chat_id


@pytest.fixture
async def stale_turns(session_factory, test_chat):
    """Insert turns in various states for testing recovery."""
    turn_ids = {
        "pending": f"turn-pending-{uuid.uuid4().hex[:8]}",
        "running": f"turn-running-{uuid.uuid4().hex[:8]}",
        "completed": f"turn-completed-{uuid.uuid4().hex[:8]}",
        "error": f"turn-error-{uuid.uuid4().hex[:8]}",
        "cancelled": f"turn-cancelled-{uuid.uuid4().hex[:8]}",
    }

    async with session_factory() as db:
        for i, (status, turn_id) in enumerate(turn_ids.items()):
            turn = AgentTurn(
                id=turn_id,
                chat_id=test_chat,
                turn_index=i,
                status=status,
                started_at=datetime.now(timezone.utc) if status != "pending" else None,
            )
            db.add(turn)
        await db.commit()

    return turn_ids


@pytest.mark.asyncio
async def test_recover_stale_agent_turns_marks_interrupted(
    session_factory, stale_turns
):
    """PENDING and RUNNING turns should be marked as INTERRUPTED."""
    from app.server.warmup import _recover_stale_agent_turns

    with patch("app.config.deploy_mode.is_local_mode", return_value=True):
        await _recover_stale_agent_turns()

    async with session_factory() as db:
        from sqlalchemy import select

        result = await db.execute(
            select(AgentTurn).where(AgentTurn.id.in_(list(stale_turns.values())))
        )
        turns = {t.id: t for t in result.scalars().all()}

    pending_turn = turns[stale_turns["pending"]]
    assert pending_turn.status == TurnStatus.INTERRUPTED.value
    assert pending_turn.completed_at is not None

    running_turn = turns[stale_turns["running"]]
    assert running_turn.status == TurnStatus.INTERRUPTED.value
    assert running_turn.completed_at is not None

    assert turns[stale_turns["completed"]].status == TurnStatus.COMPLETED.value
    assert turns[stale_turns["error"]].status == TurnStatus.ERROR.value
    assert turns[stale_turns["cancelled"]].status == TurnStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_recover_stale_agent_turns_skipped_in_sandbox():
    """Recovery should be skipped when not in local mode."""
    from app.server.warmup import _recover_stale_agent_turns

    with patch("app.config.deploy_mode.is_local_mode", return_value=False):
        await _recover_stale_agent_turns()


@pytest.mark.asyncio
async def test_recover_stale_agent_turns_idempotent(session_factory, stale_turns):
    """Running recovery twice should have no additional effect."""
    from app.server.warmup import _recover_stale_agent_turns

    with patch("app.config.deploy_mode.is_local_mode", return_value=True):
        await _recover_stale_agent_turns()
        await _recover_stale_agent_turns()

    async with session_factory() as db:
        from sqlalchemy import select

        result = await db.execute(
            select(AgentTurn).where(AgentTurn.id == stale_turns["pending"])
        )
        turn = result.scalar_one()

    assert turn.status == TurnStatus.INTERRUPTED.value


@pytest.mark.asyncio
async def test_recover_no_stale_turns_succeeds(session_factory, test_chat):
    """Recovery with no stale turns should succeed silently."""
    from app.server.warmup import _recover_stale_agent_turns

    async with session_factory() as db:
        db.add(
            AgentTurn(
                id=f"turn-completed-only-{uuid.uuid4().hex[:8]}",
                chat_id=test_chat,
                turn_index=0,
                status=TurnStatus.COMPLETED.value,
                completed_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

    with patch("app.config.deploy_mode.is_local_mode", return_value=True):
        await _recover_stale_agent_turns()


@pytest.mark.asyncio
async def test_recover_preserves_completed_at_for_terminal_turns(
    session_factory, stale_turns
):
    """Terminal turns (completed/error/cancelled) should keep their original completed_at."""
    from app.server.warmup import _recover_stale_agent_turns

    async with session_factory() as db:
        from sqlalchemy import select

        result = await db.execute(
            select(AgentTurn).where(AgentTurn.id == stale_turns["completed"])
        )
        original_completed_at = result.scalar_one().completed_at

    with patch("app.config.deploy_mode.is_local_mode", return_value=True):
        await _recover_stale_agent_turns()

    async with session_factory() as db:
        from sqlalchemy import select

        result = await db.execute(
            select(AgentTurn).where(AgentTurn.id == stale_turns["completed"])
        )
        after_recovery = result.scalar_one()

    assert after_recovery.completed_at == original_completed_at


@pytest.mark.asyncio
async def test_turn_status_enum_has_interrupted():
    """TurnStatus enum must include INTERRUPTED value."""
    assert hasattr(TurnStatus, "INTERRUPTED")
    assert TurnStatus.INTERRUPTED.value == "interrupted"
    assert len(TurnStatus) == 6
