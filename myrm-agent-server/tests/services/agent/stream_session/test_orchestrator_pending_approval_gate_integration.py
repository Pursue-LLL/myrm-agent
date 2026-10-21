"""Integration: pending-approval gate with real approval store.

The unit gate tests stub ``_count_pending_approvals``; this module exercises the
actual wiring — a real PENDING ``ApprovalRecord`` seeded in SQLite must be
counted by ``ApprovalRegistry.count_pending_for_chat`` and drive the orchestrator
to reject the new run before any session reservation is created.

[Key paths unmocked]
- ApprovalRegistry.count_pending_for_chat (real SQL via patched get_session)
- _count_pending_approvals (real helper, logs the rejection)

[Mocked]
- try_stream_reconnect / check_stream_risk / prevalidate_archive_restore_actions:
  pre-reserve gateway steps unrelated to the gate under test
- ChatSessionReservation: stand-in so the "no pending" leg stops before the
  heavy turn-body launch path
"""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database.models.approval import ApprovalRecord
from app.services.agent.gateway import AgentBusyError
from app.services.agent.stream_session import run_agent_stream

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    assert _session_factory is not None, "engine not initialized"
    return _session_factory


@pytest_asyncio.fixture(autouse=True)
async def _registry_db(tmp_path: Path):
    global _engine, _session_factory
    db_path = tmp_path / "gate_integration.db"
    _engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    async with _engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: ApprovalRecord.__table__.create(sync_conn))
    yield
    await _engine.dispose()
    _engine = None
    _session_factory = None


@pytest.fixture(autouse=True)
def _patch_session():
    @asynccontextmanager
    async def _test_get_session():
        factory = _get_session_factory()
        async with factory() as session:
            try:
                yield session
            finally:
                await session.close()

    with patch("app.services.approvals.registry.get_session", _test_get_session):
        yield


@pytest.fixture
def mock_request():
    req = MagicMock()
    req.action_mode = "general"
    req.resume_value = None
    req.chat_id = "chat-gate-integration"
    req.sibling_group_id = None
    req.timestamp = None
    req.timezone = "UTC"
    req.engine_params = None
    req.steering_id = None
    req.mention_references = None
    req.ephemeral_subagents = None
    req.blueprint_id = None
    req.message_id = "msg-gate-integration"
    req.agent_id = "default"
    req.source = "web"
    req.session_id = "session-gate-integration"
    req.subagent_ids = None
    req.context_warnings = []
    req.extra_context = {}
    req.query = "hello"
    return req


@pytest.fixture
def mock_http_request():
    http_req = MagicMock()

    async def _stream():
        yield b""

    http_req.stream = _stream
    return http_req


def _patch_gateway_prereqs(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.agent.stream_session.orchestrator.try_stream_reconnect",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.agent.stream_session.orchestrator.check_stream_risk",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.agent.stream_session.orchestrator.prevalidate_archive_restore_actions",
        AsyncMock(return_value=None),
    )


async def _seed_pending_approval(chat_id: str) -> str:
    record_id = f"record-{uuid4().hex[:8]}"
    async with _get_session_factory()() as db:
        db.add(
            ApprovalRecord(
                id=record_id,
                agent_id="default",
                chat_id=chat_id,
                status="PENDING",
                action_type="shell_command",
                created_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
                thread_id="thread-1",
                payload={"command": "ls"},
            )
        )
        await db.commit()
    return record_id


@pytest.mark.asyncio
async def test_real_pending_record_blocks_new_run_before_reservation(mock_request, mock_http_request, monkeypatch):
    """A real PENDING approval row drives the real count helper to reject the run.

    The reservation is never attempted (guard fires first), so the rejected run
    cannot strand the session reservation for the same chat.
    """
    await _seed_pending_approval(mock_request.chat_id)
    _patch_gateway_prereqs(monkeypatch)
    try_reserve_called = MagicMock(side_effect=AssertionError("try_reserve must not be called"))
    monkeypatch.setattr(
        "app.services.agent.stream_session.orchestrator.ChatSessionReservation",
        lambda: MagicMock(try_reserve=try_reserve_called),
    )

    response = await run_agent_stream(mock_request, mock_http_request)

    assert isinstance(response, StreamingResponse)
    body = "".join([chunk async for chunk in response.body_iterator])
    assert "AgentBusyError" in body


@pytest.mark.asyncio
async def test_no_pending_record_reaches_reservation(mock_request, mock_http_request, monkeypatch):
    """Without pending rows the real count helper returns 0 and flow proceeds."""
    _patch_gateway_prereqs(monkeypatch)
    saw_reservation = MagicMock(return_value=AgentBusyError("Session reservation busy (expected)"))
    monkeypatch.setattr(
        "app.services.agent.stream_session.orchestrator.ChatSessionReservation",
        lambda: MagicMock(try_reserve=saw_reservation, release=MagicMock()),
    )

    response = await run_agent_stream(mock_request, mock_http_request)

    assert isinstance(response, StreamingResponse)


@pytest.mark.asyncio
async def test_resolved_record_does_not_block(mock_request, mock_http_request, monkeypatch):
    """Only live PENDING rows gate new runs; resolved/expired rows let it through."""
    record_id = f"record-{uuid4().hex[:8]}"
    async with _get_session_factory()() as db:
        db.add(
            ApprovalRecord(
                id=record_id,
                agent_id="default",
                chat_id=mock_request.chat_id,
                status="APPROVED",
                action_type="shell_command",
                created_at=datetime.now(timezone.utc) - timedelta(minutes=10),
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                thread_id="thread-1",
                payload={"command": "ls"},
            )
        )
        await db.commit()
    _patch_gateway_prereqs(monkeypatch)
    saw_reservation = MagicMock(return_value=AgentBusyError("Session reservation busy (expected)"))
    monkeypatch.setattr(
        "app.services.agent.stream_session.orchestrator.ChatSessionReservation",
        lambda: MagicMock(try_reserve=saw_reservation, release=MagicMock()),
    )

    response = await run_agent_stream(mock_request, mock_http_request)

    assert isinstance(response, StreamingResponse)


@pytest.mark.asyncio
async def test_background_growth_record_does_not_block(mock_request, mock_http_request, monkeypatch):
    """Background growth approvals are excluded from the gate (registry semantics)."""
    record_id = f"record-{uuid4().hex[:8]}"
    from app.services.skills.growth.constants import GROWTH_ACTION_TYPES

    async with _get_session_factory()() as db:
        db.add(
            ApprovalRecord(
                id=record_id,
                agent_id="default",
                chat_id=mock_request.chat_id,
                status="PENDING",
                action_type=next(iter(GROWTH_ACTION_TYPES)),
                thread_id=None,
                payload={},
            )
        )
        await db.commit()
    _patch_gateway_prereqs(monkeypatch)
    saw_reservation = MagicMock(return_value=AgentBusyError("Session reservation busy (expected)"))
    monkeypatch.setattr(
        "app.services.agent.stream_session.orchestrator.ChatSessionReservation",
        lambda: MagicMock(try_reserve=saw_reservation, release=MagicMock()),
    )

    response = await run_agent_stream(mock_request, mock_http_request)

    assert isinstance(response, StreamingResponse)


@pytest.mark.asyncio
async def test_pending_in_other_chat_does_not_block_this_chat(mock_request, mock_http_request, monkeypatch):
    """The gate is scoped per chat_id: pending rows in another chat never block."""
    await _seed_pending_approval("chat-other-user")
    _patch_gateway_prereqs(monkeypatch)
    saw_reservation = MagicMock(return_value=AgentBusyError("Session reservation busy (expected)"))
    monkeypatch.setattr(
        "app.services.agent.stream_session.orchestrator.ChatSessionReservation",
        lambda: MagicMock(try_reserve=saw_reservation, release=MagicMock()),
    )

    response = await run_agent_stream(mock_request, mock_http_request)

    assert isinstance(response, StreamingResponse)


@pytest.mark.asyncio
async def test_resume_bypasses_gate_with_real_pending(mock_request, mock_http_request, monkeypatch):
    """Resume runs are never gated, even with real pending rows in the same chat.

    Resume is how a user approves/continues a pending tool call; gating it would
    dead-lock the approval flow. The gate must skip the count entirely.
    """
    await _seed_pending_approval(mock_request.chat_id)
    mock_request.resume_value = {"action": "approved"}
    _patch_gateway_prereqs(monkeypatch)
    saw_reservation = MagicMock(return_value=AgentBusyError("Session reservation busy (expected)"))
    monkeypatch.setattr(
        "app.services.agent.stream_session.orchestrator.ChatSessionReservation",
        lambda: MagicMock(try_reserve=saw_reservation, release=MagicMock()),
    )

    response = await run_agent_stream(mock_request, mock_http_request)

    assert isinstance(response, StreamingResponse)
