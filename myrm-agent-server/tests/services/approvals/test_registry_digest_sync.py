"""What finalizes approvals keeps the run digest's pending count in step, and the pending views agree on what counts.

The TTL sweep and the takeover resolution that a resumed chat runs both end approvals outside a button click.
"""

import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from myrm_agent_harness.agent.streaming.run_digest import RunDigestPhase
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models.approval import ApprovalRecord
from app.database.models.base import Base
from app.services.approvals.registry import ApprovalRegistry
from app.services.copilot.run_digest_store import RunDigestStore


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'approvals.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture(autouse=True)
def _registry_on_test_db(session_factory: async_sessionmaker[AsyncSession]) -> Iterator[None]:
    @asynccontextmanager
    async def get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    with patch("app.services.approvals.registry.get_session", get_session):
        yield


@pytest.fixture(autouse=True)
def _empty_digest_store() -> Iterator[None]:
    """The store is process-wide: a digest one test leaves behind must not be read by the next."""
    RunDigestStore._digests.clear()
    RunDigestStore._sessions.clear()
    with patch("app.services.copilot.run_digest_store.get_event_bus", return_value=MagicMock()):
        yield
    RunDigestStore._digests.clear()
    RunDigestStore._sessions.clear()


async def _seed(
    session_factory: async_sessionmaker[AsyncSession],
    approval_id: str,
    chat_id: str | None,
    *,
    action_type: str = "shell_command",
    thread_id: str | None = "thread-1",
    status: str = "PENDING",
    expired: bool = False,
) -> None:
    async with session_factory() as db:
        db.add(
            ApprovalRecord(
                id=approval_id,
                agent_id="agent-1",
                chat_id=chat_id,
                thread_id=thread_id,
                action_type=action_type,
                reason="test",
                severity="warning",
                payload={"cmd": "ls"},
                status=status,
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=5) if expired else None,
            )
        )
        await db.commit()


async def test_sweep_ends_the_session_an_approval_opened_for_an_idle_chat(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    for approval_id, chat_id in (("exp-1", "chat-1"), ("exp-2", "chat-2")):
        await _seed(session_factory, approval_id, chat_id, expired=True)
        RunDigestStore.set_pending_approval_count(chat_id, 1)  # what creating the approval pushed
        digest = RunDigestStore.get(chat_id)
        assert digest is not None and digest.phase == RunDigestPhase.WAITING_APPROVAL

    assert await ApprovalRegistry.cleanup_expired_approvals() == 2

    for chat_id in ("chat-1", "chat-2"):
        digest = RunDigestStore.get(chat_id)
        assert digest is not None
        assert digest.phase == RunDigestPhase.IDLE
        assert digest.pending_approval_count == 0
    assert RunDigestStore._sessions == {}


async def test_sweep_returns_a_live_run_to_running(session_factory: async_sessionmaker[AsyncSession]) -> None:
    await _seed(session_factory, "exp-3", "chat-1", expired=True)
    RunDigestStore.begin_run("chat-1")
    RunDigestStore.set_pending_approval_count("chat-1", 1)

    assert await ApprovalRegistry.cleanup_expired_approvals() == 1

    digest = RunDigestStore.get("chat-1")
    assert digest is not None
    assert digest.phase == RunDigestPhase.RUNNING
    assert digest.pending_approval_count == 0


async def test_sweep_of_an_approval_without_a_chat_does_not_try_to_sync_it(
    session_factory: async_sessionmaker[AsyncSession], caplog: pytest.LogCaptureFixture
) -> None:
    await _seed(session_factory, "exp-4", None, expired=True)

    with caplog.at_level(logging.WARNING):
        assert await ApprovalRegistry.cleanup_expired_approvals() == 1

    # A failed sync is swallowed and leaves the digests as they were, so the warning is the only trace of an attempt.
    assert "Failed to sync copilot pending approval count" not in caplog.text
    assert RunDigestStore._digests == {}


async def test_takeover_resolution_returns_the_paused_run_to_running(session_factory: async_sessionmaker[AsyncSession]) -> None:
    await _seed(session_factory, "bt-1", "chat-1", action_type="browser_takeover", thread_id=None)
    RunDigestStore.begin_run("chat-1")
    RunDigestStore.set_pending_approval_count("chat-1", 1)  # what creating the approval pushed

    assert await ApprovalRegistry.resolve_pending_browser_takeover_for_chat("chat-1") == 1

    digest = RunDigestStore.get("chat-1")
    assert digest is not None
    assert digest.phase == RunDigestPhase.RUNNING
    assert digest.pending_approval_count == 0


async def test_the_pending_views_agree_on_what_counts(session_factory: async_sessionmaker[AsyncSession]) -> None:
    # A background growth draft has no thread (None or empty): it belongs to the drafts inbox, so it is neither listed nor counted.
    await _seed(session_factory, "inline", "chat-1")
    await _seed(session_factory, "inline-growth", "chat-1", action_type="skill_draft", thread_id="thread-2")
    await _seed(session_factory, "other-chat", "chat-2")
    await _seed(session_factory, "growth-no-thread", "chat-1", action_type="skill_draft", thread_id=None)
    await _seed(session_factory, "growth-empty-thread", "chat-1", action_type="semantic_memory", thread_id="")
    await _seed(session_factory, "decided", "chat-1", status="APPROVED")

    assert await ApprovalRegistry.count_pending_for_chat("chat-1") == 2
    assert {record.id for record in await ApprovalRegistry.list_pending()} == {"inline", "inline-growth", "other-chat"}
    assert {record.id for record in await ApprovalRegistry.list_pending_growth()} == {"growth-no-thread", "growth-empty-thread"}
