"""Unit tests for ApprovalRegistry lifecycle branches.

Covers TTL expiry cleanup, the single finalize step every decision on a held channel reply goes through,
browser takeover resolution and pending-count guard — the registry capabilities exercised
by the event-branching refactor (Optimization B).
"""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.channels.types import MediaAttachment
from app.database.models.approval import ApprovalRecord
from app.database.models.base import Base
from app.services.approvals.registry import ApprovalRegistry
from tests.channels.core.outbound_testkit import make_ephemeral_doc
from tests.services.approvals.draft_testkit import draft_payload, held_reply

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_engine() -> AsyncEngine:
    assert _engine is not None, "engine not initialized"
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    assert _session_factory is not None, "session factory not initialized"
    return _session_factory


@asynccontextmanager
async def _test_get_session() -> AsyncIterator[AsyncSession]:
    async with _get_session_factory()() as session:
        try:
            yield session
        finally:
            await session.close()


@pytest.fixture(scope="session", autouse=True)
def _init_db(tmp_path_factory: pytest.TempPathFactory) -> None:
    global _engine, _session_factory
    db_path = tmp_path_factory.mktemp("registry_lifecycle") / "registry_test.db"
    _engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    yield
    _engine = None
    _session_factory = None


@pytest.fixture(autouse=True)
def _patch_session():
    with patch("app.services.approvals.registry.get_session", _test_get_session):
        yield


@pytest_asyncio.fixture(autouse=True)
async def _create_tables():
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _seed(
    record_id: str,
    *,
    action_type: str = "shell_command",
    status: str = "PENDING",
    payload: dict[str, object] | None = None,
    expires_at: datetime | None = None,
    thread_id: str | None = "thread-1",
) -> None:
    async with _get_session_factory()() as db:
        existing = await db.get(ApprovalRecord, record_id)
        if existing:
            await db.delete(existing)
            await db.commit()
        db.add(
            ApprovalRecord(
                id=record_id,
                agent_id="agent-1",
                chat_id="chat-1",
                thread_id=thread_id,
                action_type=action_type,
                reason="test",
                severity="warning",
                payload=payload or {"cmd": "ls"},
                status=status,
                expires_at=expires_at,
            )
        )
        await db.commit()


class TestCleanupExpiredApprovals:
    @pytest.mark.asyncio
    async def test_no_expired_returns_zero(self) -> None:
        assert await ApprovalRegistry.cleanup_expired_approvals() == 0

    @pytest.mark.asyncio
    async def test_expired_pending_marked_timeout(self) -> None:
        await _seed(
            "exp-1",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        bus = MagicMock()
        with patch("app.services.approvals.registry.get_event_bus", return_value=bus):
            count = await ApprovalRegistry.cleanup_expired_approvals()

        assert count == 1
        bus.publish.assert_called_once()
        event = bus.publish.call_args.args[0]
        assert event.data["decision"] == "deny"
        assert event.data["thread_id"] == "thread-1"

    @pytest.mark.asyncio
    async def test_future_expiry_not_touched(self) -> None:
        await _seed(
            "exp-2",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        bus = MagicMock()
        with patch("app.services.approvals.registry.get_event_bus", return_value=bus):
            count = await ApprovalRegistry.cleanup_expired_approvals()

        assert count == 0
        bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_outbound_auto_send_on_ttl(self) -> None:
        await _seed(
            "exp-3",
            action_type="outbound_draft",
            payload={"draft_timeout_action": "auto_send", "draft_content": "hello"},
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        bus = MagicMock()
        with (
            patch("app.services.approvals.registry.get_event_bus", return_value=bus),
            patch(
                "app.services.approvals.outbound_draft.send_outbound_draft_payload",
                new=AsyncMock(return_value=True),
            ) as send_mock,
        ):
            count = await ApprovalRegistry.cleanup_expired_approvals()

        assert count == 1
        send_mock.assert_awaited_once()


class TestOutboundDraftRelease:
    """A draft that will never be sent must not leave its temp attachments behind."""

    @staticmethod
    async def _seed_draft(
        record_id: str, shot: MediaAttachment, *, timeout_action: str = "auto_reject", **kwargs: object
    ) -> None:
        payload = draft_payload(held_reply(shot), draft_timeout_action=timeout_action)
        await _seed(record_id, action_type="outbound_draft", thread_id=None, payload=payload, **kwargs)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_rejected_draft_deletes_its_temp_attachments(self) -> None:
        shot = make_ephemeral_doc("shot.png")
        await self._seed_draft("od-reject", shot)

        record = await ApprovalRegistry.resolve_approval("od-reject", "deny")

        assert record is not None and record.status == "REJECTED"
        assert not Path(shot.path).exists()

    @pytest.mark.asyncio
    async def test_approved_draft_keeps_its_temp_attachments_for_the_send(self) -> None:
        shot = make_ephemeral_doc("shot.png")
        await self._seed_draft("od-approve", shot)

        with patch("app.services.approvals.outbound_draft.send_outbound_draft_payload", new=AsyncMock(return_value=True)) as send:
            await ApprovalRegistry.resolve_approval("od-approve", "approve")

        try:
            send.assert_awaited_once()
            assert Path(shot.path).exists()
        finally:
            Path(shot.path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_expired_draft_deletes_its_temp_attachments(self) -> None:
        shot = make_ephemeral_doc("shot.png")
        await self._seed_draft("od-expire", shot, expires_at=datetime.now(timezone.utc) - timedelta(minutes=5))

        with patch("app.services.approvals.registry.get_event_bus", return_value=MagicMock()):
            assert await ApprovalRegistry.cleanup_expired_approvals() == 1

        assert not Path(shot.path).exists()

    @pytest.mark.asyncio
    async def test_auto_sent_expired_draft_keeps_its_temp_attachments(self) -> None:
        shot = make_ephemeral_doc("shot.png")
        await self._seed_draft(
            "od-auto-send", shot, timeout_action="auto_send", expires_at=datetime.now(timezone.utc) - timedelta(minutes=5)
        )

        with (
            patch("app.services.approvals.registry.get_event_bus", return_value=MagicMock()),
            patch("app.services.approvals.outbound_draft.send_outbound_draft_payload", new=AsyncMock(return_value=True)),
        ):
            assert await ApprovalRegistry.cleanup_expired_approvals() == 1

        try:
            assert Path(shot.path).exists()
        finally:
            Path(shot.path).unlink(missing_ok=True)


class TestHeldReplyFunnel:
    """Every door that decides on a held reply (WebUI, IM button, batch, TTL sweeper) reaches one finalize step, once."""

    @pytest.fixture
    def finalize(self) -> Iterator[AsyncMock]:
        with patch("app.services.approvals.registry.finalize_outbound_draft", new_callable=AsyncMock) as finalize:
            yield finalize

    @staticmethod
    async def _seed_draft(record_id: str, **kwargs: object) -> None:
        await _seed(record_id, action_type="outbound_draft", thread_id=None, payload=draft_payload(held_reply()), **kwargs)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("decision", "status"), [("approve", "APPROVED"), ("deny", "REJECTED")])
    async def test_a_decision_is_finalized_with_its_outcome(self, finalize: AsyncMock, decision: str, status: str) -> None:
        await self._seed_draft(f"fn-{decision}")

        record = await ApprovalRegistry.resolve_approval(f"fn-{decision}", decision)

        assert record is not None and record.status == status
        finalize.assert_awaited_once_with(record)

    @pytest.mark.asyncio
    async def test_a_second_decision_finalizes_nothing(self, finalize: AsyncMock) -> None:
        await self._seed_draft("fn-twice")
        await ApprovalRegistry.resolve_approval("fn-twice", "approve")

        assert await ApprovalRegistry.resolve_approval("fn-twice", "deny") is None

        finalize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_the_reviewers_edit_is_what_gets_sent(self) -> None:
        await self._seed_draft("fn-edit")

        with patch("app.services.approvals.outbound_draft.send_outbound_draft_payload", new=AsyncMock(return_value=True)) as send:
            await ApprovalRegistry.resolve_approval("fn-edit", "approve", edited_payload={"draft_content": "edited by reviewer"})

        assert send.await_args.args[0]["draft_content"] == "edited by reviewer"

    @pytest.mark.asyncio
    async def test_other_approvals_are_not_finalized_as_held_replies(self, finalize: AsyncMock) -> None:
        await _seed("fn-tool")

        await ApprovalRegistry.resolve_approval("fn-tool", "approve")

        finalize.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_expired_drafts_are_finalized_with_their_timeout_outcome(self, finalize: AsyncMock) -> None:
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        for record_id, action in (("fn-auto-send", "auto_send"), ("fn-auto-reject", "auto_reject")):
            await _seed(
                record_id,
                action_type="outbound_draft",
                thread_id=None,
                payload={**draft_payload(held_reply()), "draft_timeout_action": action},
                expires_at=past,
            )
        await _seed("fn-tool-expired", expires_at=past)

        with patch("app.services.approvals.registry.get_event_bus", return_value=MagicMock()):
            assert await ApprovalRegistry.cleanup_expired_approvals() == 3

        outcomes = {call.args[0].id: call.args[0].status for call in finalize.await_args_list}
        assert outcomes == {"fn-auto-send": "APPROVED", "fn-auto-reject": "TIMEOUT"}


class TestFindPendingOutboundDrafts:
    """``/draft`` finds a held reply by the start of its id, and can reach nothing else."""

    @staticmethod
    async def _seed_draft(record_id: str, **kwargs: object) -> None:
        await _seed(record_id, action_type="outbound_draft", thread_id=None, payload=draft_payload(held_reply()), **kwargs)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_a_prefix_finds_the_pending_held_reply(self) -> None:
        await self._seed_draft("3f9a1c2e5b7d4a6f8c0e1b2d3a4f5e6d")

        found = await ApprovalRegistry.find_pending_outbound_drafts("3f9a1c")

        assert [record.id for record in found] == ["3f9a1c2e5b7d4a6f8c0e1b2d3a4f5e6d"]

    @pytest.mark.asyncio
    async def test_only_pending_held_replies_match(self) -> None:
        await self._seed_draft("aaaa0001", status="APPROVED")
        await self._seed_draft("aaaa0002", status="TIMEOUT")
        await _seed("aaaa0003")
        await self._seed_draft("aaaa0004")

        found = await ApprovalRegistry.find_pending_outbound_drafts("aaaa")

        assert [record.id for record in found] == ["aaaa0004"]

    @pytest.mark.asyncio
    async def test_a_prefix_shared_by_many_yields_two_which_is_enough_to_call_it_ambiguous(self) -> None:
        for suffix in "123":
            await self._seed_draft(f"bbbb000{suffix}")

        assert len(await ApprovalRegistry.find_pending_outbound_drafts("bbbb")) == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize("wildcard", ["%", "_", "cccc_00_", "cccc%"])
    async def test_like_wildcards_match_literally(self, wildcard: str) -> None:
        await self._seed_draft("cccc0001")

        assert await ApprovalRegistry.find_pending_outbound_drafts(wildcard) == []


class TestResolveBrowserTakeover:
    @pytest.mark.asyncio
    async def test_empty_chat_id_returns_zero(self) -> None:
        count = await ApprovalRegistry.resolve_pending_browser_takeover_for_chat("  ")
        assert count == 0

    @pytest.mark.asyncio
    async def test_approves_pending_takeover(self) -> None:
        await _seed(
            "bt-1",
            action_type="browser_takeover",
            thread_id=None,
        )
        count = await ApprovalRegistry.resolve_pending_browser_takeover_for_chat("chat-1", decision="approve")
        assert count == 1

    @pytest.mark.asyncio
    async def test_denies_pending_takeover(self) -> None:
        await _seed(
            "bt-2",
            action_type="browser_takeover",
            thread_id=None,
        )
        count = await ApprovalRegistry.resolve_pending_browser_takeover_for_chat("chat-1", decision="deny")
        assert count == 1


class TestCountPendingForChat:
    @pytest.mark.asyncio
    async def test_empty_chat_id_returns_zero(self) -> None:
        assert await ApprovalRegistry.count_pending_for_chat("") == 0

    @pytest.mark.asyncio
    async def test_counts_only_inline_pending(self) -> None:
        await _seed("cp-1", thread_id="thread-a")
        count = await ApprovalRegistry.count_pending_for_chat("chat-1")
        assert count >= 1


class TestListPendingGrowth:
    @pytest.mark.asyncio
    async def test_returns_only_background_growth(self) -> None:
        await _seed("lg-bg", action_type="skill_draft", thread_id=None)
        await _seed("lg-inline", action_type="skill_draft", thread_id="thread-x")

        growth = await ApprovalRegistry.list_pending_growth(limit=50)
        ids = {rec.id for rec in growth}
        assert "lg-bg" in ids
        assert "lg-inline" not in ids

    @pytest.mark.asyncio
    async def test_excludes_non_pending_and_resolved(self) -> None:
        await _seed("lg-resolved", action_type="skill_draft", thread_id=None, status="APPROVED")

        growth = await ApprovalRegistry.list_pending_growth(limit=50)
        ids = {rec.id for rec in growth}
        assert "lg-resolved" not in ids


class TestChannelNativeApprovalBlock:
    @pytest.mark.asyncio
    async def test_channel_pending_approval_pushes_native_block(self) -> None:
        """A PENDING approval for a non-web channel chat pushes a Native Approval Block."""
        from app.database.models.chat import Chat

        async with _get_session_factory()() as db:
            chat = Chat(
                id="chat-channel-1",
                source="telegram",
                channel_session_key="telegram:user:peer-777",
            )
            db.add(chat)
            await db.commit()

        gateway = AsyncMock()
        bus = MagicMock()
        with (
            patch("app.services.approvals.registry.get_event_bus", return_value=bus),
            patch("app.core.channel_bridge.get_channel_gateway", return_value=gateway),
        ):
            await ApprovalRegistry.create_approval(
                agent_id="chan-agent",
                action_type="shell_command",
                payload={"cmd": "ls"},
                reason="needs review",
                chat_id="chat-channel-1",
            )

        gateway.publish.assert_awaited_once()
        msg = gateway.publish.await_args.args[0]
        assert msg.channel == "telegram"
        assert msg.recipient_id == "peer-777"
        assert msg.content is not None
        assert "Approval Required" in msg.content

    @pytest.mark.asyncio
    async def test_web_chat_does_not_push_native_block(self) -> None:
        """Web chats do not trigger the native approval block push."""
        from app.database.models.chat import Chat

        async with _get_session_factory()() as db:
            chat = Chat(
                id="chat-web-1",
                source="web",
                channel_session_key=None,
            )
            db.add(chat)
            await db.commit()

        gateway = AsyncMock()
        bus = MagicMock()
        with (
            patch("app.services.approvals.registry.get_event_bus", return_value=bus),
            patch("app.core.channel_bridge.get_channel_gateway", return_value=gateway),
        ):
            await ApprovalRegistry.create_approval(
                agent_id="web-agent",
                action_type="shell_command",
                payload={"cmd": "ls"},
                reason="needs review",
                chat_id="chat-web-1",
            )

        gateway.publish.assert_not_awaited()
