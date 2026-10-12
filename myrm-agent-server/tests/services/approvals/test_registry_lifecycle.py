"""Unit tests for ApprovalRegistry lifecycle branches.

Covers TTL expiry cleanup, outbound draft auto-send, browser takeover
resolution and pending-count guard — the registry capabilities exercised
by the event-branching refactor (Optimization B).
"""

import dataclasses
import logging
from collections.abc import AsyncIterator
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

from app.channels.types import ActionButton, MediaAttachment, MediaType, OutboundMessage
from app.database.models.approval import ApprovalRecord
from app.database.models.base import Base
from app.services.approvals.registry import (
    ApprovalRegistry,
    send_outbound_draft_payload,
)
from tests.channels.core.outbound_testkit import make_ephemeral_doc

_HANDOFF_BUTTON = ActionButton(label="Continue in browser", action_id="web:continue_chat", url="https://example.test/chat/abc")

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
                "app.services.approvals.registry.send_outbound_draft_payload",
                new=AsyncMock(return_value=True),
            ) as send_mock,
        ):
            count = await ApprovalRegistry.cleanup_expired_approvals()

        assert count == 1
        send_mock.assert_awaited_once()


def _held_reply(*media: MediaAttachment, content: str = "hello") -> OutboundMessage:
    return OutboundMessage(
        channel="telegram",
        recipient_id="peer-1",
        content=content,
        user_id="owner-1",
        media=media,
        components=((_HANDOFF_BUTTON,),),
        reply_to_id="m-1",
        thread_id="th-1",
        metadata={"locale": "zh"},
    )


def _draft_payload(reply: OutboundMessage, *, draft_content: str | None = None, **extra: object) -> dict[str, object]:
    """Payload as the router stores it: the text stays editable, the rest of the reply is frozen."""
    return {"draft_content": reply.content if draft_content is None else draft_content, "outbound": reply.to_dict(), **extra}


class TestSendOutboundDraftPayload:
    @pytest.mark.asyncio
    async def test_blank_draft_without_attachments_is_skipped(self) -> None:
        gateway = AsyncMock()
        with patch("app.core.channel_bridge.get_channel_gateway", return_value=gateway):
            sent = await send_outbound_draft_payload(_draft_payload(_held_reply(), draft_content="  "), "agent-1", "rec-1")

        assert sent is False
        gateway.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sends_the_held_reply_with_the_reviewed_text(self, tmp_path: Path) -> None:
        report = MediaAttachment(media_type=MediaType.DOCUMENT, path=str(tmp_path / "report.pdf"), filename="report.pdf")
        reply = _held_reply(report)
        gateway = AsyncMock()
        with patch("app.core.channel_bridge.get_channel_gateway", return_value=gateway):
            sent = await send_outbound_draft_payload(
                _draft_payload(reply, draft_content="edited by reviewer"), "agent-1", "rec-2"
            )

        assert sent is True
        gateway.publish.assert_awaited_once()
        assert gateway.publish.await_args.args[0] == dataclasses.replace(reply, content="edited by reviewer")

    @pytest.mark.asyncio
    async def test_attachment_only_draft_is_sent(self, tmp_path: Path) -> None:
        reply = _held_reply(MediaAttachment(media_type=MediaType.DOCUMENT, path=str(tmp_path / "a.pdf")), content="")
        gateway = AsyncMock()
        with patch("app.core.channel_bridge.get_channel_gateway", return_value=gateway):
            sent = await send_outbound_draft_payload(_draft_payload(reply), "agent-1", "rec-3")

        assert sent is True
        assert gateway.publish.await_args.args[0] == reply

    @pytest.mark.asyncio
    async def test_payload_without_a_snapshot_is_not_sent(self, caplog: pytest.LogCaptureFixture) -> None:
        pre_snapshot = {
            "draft_content": "hello",
            "channel": "telegram",
            "recipient_id": "peer-1",
            "draft_media": [{"url": "https://x/a.png", "type": "image"}],
        }
        gateway = AsyncMock()
        with patch("app.core.channel_bridge.get_channel_gateway", return_value=gateway), caplog.at_level(logging.WARNING):
            sent = await send_outbound_draft_payload(pre_snapshot, "agent-1", "rec-4")

        assert sent is False
        gateway.publish.assert_not_awaited()
        assert any(r.levelno == logging.WARNING and "rec-4" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_undecodable_snapshot_is_not_sent(self, caplog: pytest.LogCaptureFixture) -> None:
        gateway = AsyncMock()
        with patch("app.core.channel_bridge.get_channel_gateway", return_value=gateway), caplog.at_level(logging.WARNING):
            sent = await send_outbound_draft_payload(
                {"draft_content": "hello", "outbound": {"channel": "telegram"}}, "agent-1", "rec-5"
            )

        assert sent is False
        gateway.publish.assert_not_awaited()
        assert any("rec-5" in r.getMessage() for r in caplog.records)


class TestOutboundDraftRelease:
    """A draft that will never be sent must not leave its temp attachments behind."""

    @staticmethod
    async def _seed_draft(
        record_id: str, shot: MediaAttachment, *, timeout_action: str = "auto_reject", **kwargs: object
    ) -> None:
        payload = _draft_payload(_held_reply(shot), draft_timeout_action=timeout_action)
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

        await ApprovalRegistry.resolve_approval("od-approve", "approve")

        try:
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
            patch("app.services.approvals.registry.send_outbound_draft_payload", new=AsyncMock(return_value=True)),
        ):
            assert await ApprovalRegistry.cleanup_expired_approvals() == 1

        try:
            assert Path(shot.path).exists()
        finally:
            Path(shot.path).unlink(missing_ok=True)


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
