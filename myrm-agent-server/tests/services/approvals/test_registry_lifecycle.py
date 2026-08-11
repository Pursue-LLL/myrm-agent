"""Unit tests for ApprovalRegistry lifecycle branches.

Covers TTL expiry cleanup, outbound draft auto-send, browser takeover
resolution and pending-count guard — the registry capabilities exercised
by the event-branching refactor (Optimization B).
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models.approval import ApprovalRecord
from app.database.models.base import Base
from app.services.approvals.registry import ApprovalRegistry, send_outbound_draft_payload

_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


@asynccontextmanager
async def _test_get_session() -> AsyncIterator[AsyncSession]:
    async with _session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


@pytest.fixture(autouse=True)
def _patch_session():
    with patch("app.services.approvals.registry.get_session", _test_get_session):
        yield


@pytest.fixture(scope="module", autouse=True)
def _create_tables():
    async def _setup():
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_setup())
    yield

    async def _teardown():
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await _engine.dispose()

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_teardown())


async def _seed(
    record_id: str,
    *,
    action_type: str = "shell_command",
    status: str = "PENDING",
    payload: dict[str, object] | None = None,
    expires_at: datetime | None = None,
    thread_id: str | None = "thread-1",
) -> None:
    async with _session_factory() as db:
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


class TestSendOutboundDraftPayload:
    @pytest.mark.asyncio
    async def test_empty_content_skipped(self) -> None:
        sent = await send_outbound_draft_payload({"draft_content": "  "}, "agent-1", "rec-1")
        assert sent is False

    @pytest.mark.asyncio
    async def test_sends_media_and_content(self) -> None:
        gateway = AsyncMock()
        with patch("app.core.channel_bridge.get_channel_gateway", return_value=gateway):
            sent = await send_outbound_draft_payload(
                {
                    "draft_content": "hello",
                    "channel": "telegram",
                    "recipient_id": "peer-1",
                    "draft_media": [{"url": "https://x/a.png", "type": "image"}],
                },
                "agent-1",
                "rec-2",
            )

        assert sent is True
        gateway.publish.assert_awaited_once()
        msg = gateway.publish.await_args.args[0]
        assert msg.content == "hello"
        assert msg.channel == "telegram"
        assert msg.recipient_id == "peer-1"

    @pytest.mark.asyncio
    async def test_invalid_media_type_falls_back_to_document(self) -> None:
        from app.channels.types.messages import MediaType

        gateway = AsyncMock()
        with patch("app.core.channel_bridge.get_channel_gateway", return_value=gateway):
            sent = await send_outbound_draft_payload(
                {
                    "draft_content": "hello",
                    "draft_media": [{"url": "https://x/b.bin", "type": "not-a-real-type"}],
                },
                "agent-1",
                "rec-3",
            )

        assert sent is True
        msg = gateway.publish.await_args.args[0]
        assert msg.media is not None
        assert msg.media[0].media_type == MediaType.DOCUMENT

    @pytest.mark.asyncio
    async def test_non_dict_media_item_ignored(self) -> None:
        gateway = AsyncMock()
        with patch("app.core.channel_bridge.get_channel_gateway", return_value=gateway):
            sent = await send_outbound_draft_payload(
                {
                    "draft_content": "hello",
                    "draft_media": ["raw-string", {"url": ""}, None],
                },
                "agent-1",
                "rec-4",
            )

        assert sent is True
        msg = gateway.publish.await_args.args[0]
        assert msg.media is None


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

        async with _session_factory() as db:
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

        async with _session_factory() as db:
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
