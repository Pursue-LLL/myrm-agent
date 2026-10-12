"""Integration tests for _handle_action_button_approval (ActionButton callback path).

Covers the full handler flow including parsing, authorisation, DB resolve,
message editing, and agent resume / SSE fallback. DB operations use a real
SQLite in-memory database; only SSE event bus is mocked.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.channels.routing.commands import RouterCommandsMixin
from app.channels.routing.router_keys import routing_session_key
from app.channels.routing.router_models import _ActiveTask
from app.channels.types import InboundMessage
from app.database.models.approval import ApprovalRecord
from app.database.models.base import Base

_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
_factory = async_sessionmaker(_engine, expire_on_commit=False)


@asynccontextmanager
async def _test_session() -> AsyncIterator[AsyncSession]:
    async with _factory() as session:
        try:
            yield session
        finally:
            await session.close()


@pytest.fixture(autouse=True, scope="module")
def _create_tables():
    loop = asyncio.new_event_loop()
    loop.run_until_complete(_async_create())
    yield
    loop.run_until_complete(_async_drop())
    loop.close()


async def _async_create():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _async_drop():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _engine.dispose()


@pytest.fixture(autouse=True)
def _patch_db():
    with patch(
        "app.services.approvals.registry.get_session",
        _test_session,
    ):
        yield


@pytest.fixture(autouse=True)
def _patch_events():
    mock_bus = MagicMock()
    with (
        patch(
            "app.services.approvals.registry.get_event_bus",
            return_value=mock_bus,
        ),
        patch(
            "app.services.event.app_event_bus.get_event_bus",
            return_value=mock_bus,
        ),
    ):
        yield mock_bus


def _make_active_task(
    requester_id: str = "alice",
    *,
    channel: str = "telegram",
    chat_id: str = "chat-1",
) -> _ActiveTask:
    loop = asyncio.new_event_loop()
    try:
        future = loop.create_future()
        future.set_result(None)
    finally:
        loop.close()
    return _ActiveTask(
        task=future,  # type: ignore[arg-type]
        cancel_token=MagicMock(),
        channel=channel,
        chat_id=chat_id,
        placeholder_id=None,
        started_at=0.0,
        requester_id=requester_id,
    )


@dataclass(slots=True)
class _Host(RouterCommandsMixin):
    _active_tasks: dict[str, _ActiveTask] = field(default_factory=dict)
    _approval_msg_ids: dict[str, str] = field(default_factory=dict)
    _approval_co_approvers: frozenset[str] = field(default_factory=frozenset)
    _bus: MagicMock = field(default_factory=MagicMock)
    _gate: MagicMock = field(default_factory=MagicMock)
    # The router decides who the owner is; each test states whether the clicker passes that check.
    _check_admin_permission: AsyncMock = field(default_factory=lambda: AsyncMock(return_value=True))


def _host(**overrides: Any) -> _Host:  # noqa: ANN401
    bus = MagicMock()
    bus.publish_outbound = AsyncMock()
    bus.edit_channel_message = AsyncMock()
    gate = MagicMock()
    gate.submit = MagicMock()
    return _Host(_bus=bus, _gate=gate, **overrides)


def _action_msg(
    content: str,
    *,
    sender_id: str = "alice",
    channel: str = "telegram",
    chat_id: str = "chat-1",
    is_group: bool = False,
    origin_message_id: str | None = "orig-123",
    locale: str | None = None,
) -> InboundMessage:
    metadata: dict[str, object] = {}
    if origin_message_id:
        metadata["origin_message_id"] = origin_message_id
    if locale:
        metadata["locale"] = locale
    metadata["username"] = sender_id
    return InboundMessage(
        channel=channel,
        sender_id=sender_id,
        content=content,
        chat_id=chat_id,
        is_group=is_group,
        metadata=metadata,
    )


async def _seed(record_id: str = "appr-001", status: str = "PENDING", action_type: str = "shell_command") -> str:
    async with _test_session() as db:
        existing = await db.get(ApprovalRecord, record_id)
        if existing:
            await db.delete(existing)
            await db.commit()
        db.add(
            ApprovalRecord(
                id=record_id,
                agent_id="agent-1",
                chat_id="chat-1",
                thread_id="thread-1",
                action_type=action_type,
                reason="test",
                severity="warning",
                payload={"cmd": "ls"},
                status=status,
            )
        )
        await db.commit()
    return record_id


async def _status_of(record_id: str) -> str:
    async with _test_session() as db:
        record = await db.get(ApprovalRecord, record_id)
        assert record is not None
        return record.status


class TestActionButtonParsing:
    @pytest.mark.asyncio
    async def test_malformed_content_is_rejected(self):
        host = _host()
        msg = _action_msg("bad-content")
        await host._handle_action_button_approval(msg)
        host._gate.submit.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_parts_is_rejected(self):
        host = _host()
        msg = _action_msg("approval:approve")
        await host._handle_action_button_approval(msg)
        host._gate.submit.assert_not_called()

    @pytest.mark.asyncio
    async def test_wrong_prefix_is_rejected(self):
        host = _host()
        msg = _action_msg("reaction:approve:id-123")
        await host._handle_action_button_approval(msg)
        host._gate.submit.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_action_is_rejected(self):
        host = _host()
        msg = _action_msg("approval:cancel:id-123")
        await host._handle_action_button_approval(msg)
        host._gate.submit.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_content_is_rejected(self):
        host = _host()
        msg = _action_msg("")
        await host._handle_action_button_approval(msg)
        host._gate.submit.assert_not_called()


class TestActionButtonAuthorisation:
    @pytest.mark.asyncio
    async def test_group_bystander_is_blocked(self):
        host = _host()
        key = routing_session_key("telegram", "chat-1")
        host._active_tasks[key] = _make_active_task("alice")
        await _seed("appr-auth-1")
        msg = _action_msg(
            "approval:approve:appr-auth-1",
            sender_id="bob",
            is_group=True,
        )
        await host._handle_action_button_approval(msg)
        host._gate.submit.assert_not_called()

    @pytest.mark.asyncio
    async def test_group_requester_is_allowed(self):
        host = _host()
        key = routing_session_key("telegram", "chat-1")
        host._active_tasks[key] = _make_active_task("alice")
        await _seed("appr-auth-2")
        msg = _action_msg(
            "approval:approve:appr-auth-2",
            sender_id="alice",
            is_group=True,
        )
        await host._handle_action_button_approval(msg)
        host._gate.submit.assert_called_once()

    @pytest.mark.asyncio
    async def test_group_co_approver_is_allowed(self):
        host = _host(_approval_co_approvers=frozenset({"oncall"}))
        key = routing_session_key("telegram", "chat-1")
        host._active_tasks[key] = _make_active_task("alice")
        await _seed("appr-auth-3")
        msg = _action_msg(
            "approval:approve:appr-auth-3",
            sender_id="oncall",
            is_group=True,
        )
        await host._handle_action_button_approval(msg)
        host._gate.submit.assert_called_once()

    @pytest.mark.asyncio
    async def test_dm_bypasses_bystander_check(self):
        host = _host()
        key = routing_session_key("telegram", "chat-1")
        host._active_tasks[key] = _make_active_task("alice")
        await _seed("appr-auth-4")
        msg = _action_msg(
            "approval:approve:appr-auth-4",
            sender_id="bob",
            is_group=False,
        )
        await host._handle_action_button_approval(msg)
        host._gate.submit.assert_called_once()


class TestActionButtonResolve:
    @pytest.mark.asyncio
    async def test_approve_resumes_agent(self):
        host = _host()
        key = routing_session_key("telegram", "chat-1")
        host._active_tasks[key] = _make_active_task("alice")
        await _seed("appr-resolve-1")
        msg = _action_msg("approval:approve:appr-resolve-1")
        await host._handle_action_button_approval(msg)

        host._gate.submit.assert_called_once()
        resume = host._gate.submit.call_args[0][0].resume_value
        assert resume["decisions"][0]["type"] == "approve"

    @pytest.mark.asyncio
    async def test_deny_resumes_agent(self):
        host = _host()
        key = routing_session_key("telegram", "chat-1")
        host._active_tasks[key] = _make_active_task("alice")
        await _seed("appr-resolve-2")
        msg = _action_msg("approval:deny:appr-resolve-2")
        await host._handle_action_button_approval(msg)

        host._gate.submit.assert_called_once()
        resume = host._gate.submit.call_args[0][0].resume_value
        assert resume["decisions"][0]["type"] == "reject"

    @pytest.mark.asyncio
    async def test_duplicate_click_does_not_resume(self):
        host = _host()
        key = routing_session_key("telegram", "chat-1")
        host._active_tasks[key] = _make_active_task("alice")
        await _seed("appr-resolve-3")

        msg = _action_msg("approval:approve:appr-resolve-3")
        await host._handle_action_button_approval(msg)
        host._gate.submit.assert_called_once()

        host._gate.submit.reset_mock()
        msg2 = _action_msg("approval:deny:appr-resolve-3")
        await host._handle_action_button_approval(msg2)
        host._gate.submit.assert_not_called()

    @pytest.mark.asyncio
    async def test_nonexistent_id_does_not_resume(self):
        host = _host()
        msg = _action_msg("approval:approve:nonexistent-id-xyz")
        await host._handle_action_button_approval(msg)
        host._gate.submit.assert_not_called()


class TestActionButtonMessageEditing:
    @pytest.mark.asyncio
    async def test_edits_original_message_on_approve(self):
        host = _host()
        key = routing_session_key("telegram", "chat-1")
        host._active_tasks[key] = _make_active_task("alice")
        await _seed("appr-edit-1")
        msg = _action_msg("approval:approve:appr-edit-1", origin_message_id="orig-999")
        await host._handle_action_button_approval(msg)

        host._bus.edit_channel_message.assert_awaited_once()
        call_args = host._bus.edit_channel_message.call_args
        assert call_args[0][2] == "orig-999"
        assert "Approved" in call_args[0][3]

    @pytest.mark.asyncio
    async def test_no_edit_when_origin_missing(self):
        host = _host()
        key = routing_session_key("telegram", "chat-1")
        host._active_tasks[key] = _make_active_task("alice")
        await _seed("appr-edit-2")
        msg = _action_msg(
            "approval:approve:appr-edit-2",
            origin_message_id=None,
        )
        await host._handle_action_button_approval(msg)
        host._bus.edit_channel_message.assert_not_awaited()
        host._gate.submit.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("action", "locale", "expected"),
        [
            ("approve", None, "✅ Approved by alice"),
            ("deny", None, "🚫 Denied by alice"),
            ("approve", "zh-CN", "✅ 已由 alice 批准"),
            ("deny", "zh-CN", "🚫 已由 alice 拒绝"),
        ],
    )
    async def test_status_line_reads_naturally_in_the_clickers_language(self, action, locale, expected):
        host = _host()
        host._active_tasks[routing_session_key("telegram", "chat-1")] = _make_active_task("alice")
        record_id = await _seed(f"appr-status-{action}-{locale}")
        await host._handle_action_button_approval(_action_msg(f"approval:{action}:{record_id}", locale=locale))

        assert host._bus.edit_channel_message.call_args[0][3] == expected


class TestActionButtonSSEFallback:
    @pytest.mark.asyncio
    async def test_no_active_task_publishes_sse_event(self):
        mock_bus = MagicMock()
        host = _host()
        await _seed("appr-sse-1")
        msg = _action_msg("approval:approve:appr-sse-1")

        with patch(
            "app.services.event.app_event_bus.get_event_bus",
            return_value=mock_bus,
        ):
            await host._handle_action_button_approval(msg)

        host._gate.submit.assert_not_called()
        mock_bus.publish.assert_called()
        event = mock_bus.publish.call_args[0][0]
        assert event.data["approval_id"] == "appr-sse-1"
        assert event.data["decision"] == "approve"


class TestHeldReplyAuthorisation:
    """A held channel reply (``outbound_draft``) is decided by the owner alone."""

    @pytest.fixture(autouse=True)
    def send_draft(self) -> Iterator[AsyncMock]:
        with patch("app.services.approvals.registry.send_outbound_draft_payload", new_callable=AsyncMock) as sent:
            yield sent

    @pytest.mark.asyncio
    async def test_the_owner_approves_and_the_reply_is_sent(self, send_draft):
        host = _host()
        await _seed("appr-draft-1", action_type="outbound_draft")

        await host._handle_action_button_approval(_action_msg("approval:approve:appr-draft-1", sender_id="owner"))

        send_draft.assert_awaited_once()
        assert await _status_of("appr-draft-1") == "APPROVED"
        host._gate.submit.assert_not_called()

    @pytest.mark.asyncio
    async def test_the_owner_denies_and_nothing_is_sent(self, send_draft):
        host = _host()
        await _seed("appr-draft-2", action_type="outbound_draft")

        await host._handle_action_button_approval(_action_msg("approval:deny:appr-draft-2", sender_id="owner"))

        send_draft.assert_not_awaited()
        assert await _status_of("appr-draft-2") == "REJECTED"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("is_group", [False, True], ids=["dm", "group"])
    async def test_anyone_else_is_refused_and_told_where_to_decide(self, send_draft, is_group):
        host = _host()
        host._check_admin_permission.return_value = False
        await _seed(f"appr-draft-3-{is_group}", action_type="outbound_draft")

        await host._handle_action_button_approval(
            _action_msg(f"approval:approve:appr-draft-3-{is_group}", sender_id="bystander", is_group=is_group)
        )

        send_draft.assert_not_awaited()
        assert await _status_of(f"appr-draft-3-{is_group}") == "PENDING", "the owner can still decide"
        host._bus.edit_channel_message.assert_not_awaited()
        host._bus.publish_outbound.assert_awaited_once()
        reply = host._bus.publish_outbound.call_args[0][0]
        assert (reply.channel, reply.recipient_id) == ("telegram", "chat-1")
        assert "Only an admin can decide" in reply.content

    @pytest.mark.asyncio
    async def test_running_the_chats_task_grants_nothing_over_a_held_reply(self, send_draft):
        host = _host()
        host._check_admin_permission.return_value = False
        host._active_tasks[routing_session_key("telegram", "chat-1")] = _make_active_task("bob")
        await _seed("appr-draft-4", action_type="outbound_draft")

        await host._handle_action_button_approval(_action_msg("approval:approve:appr-draft-4", sender_id="bob", is_group=True))

        send_draft.assert_not_awaited()
        assert await _status_of("appr-draft-4") == "PENDING"

    @pytest.mark.asyncio
    async def test_the_owner_is_not_blocked_by_someone_elses_running_task(self, send_draft):
        host = _host()
        host._active_tasks[routing_session_key("telegram", "chat-1")] = _make_active_task("alice")
        await _seed("appr-draft-5", action_type="outbound_draft")

        await host._handle_action_button_approval(_action_msg("approval:approve:appr-draft-5", sender_id="owner", is_group=True))

        send_draft.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_tool_approvals_do_not_ask_for_the_owner_check(self):
        host = _host()
        host._check_admin_permission.return_value = False
        host._active_tasks[routing_session_key("telegram", "chat-1")] = _make_active_task("alice")
        await _seed("appr-tool-1")

        await host._handle_action_button_approval(_action_msg("approval:approve:appr-tool-1"))

        host._gate.submit.assert_called_once()
        host._check_admin_permission.assert_not_awaited()


class TestNotificationCardContract:
    @pytest.mark.asyncio
    async def test_every_button_of_the_owner_card_is_understood_by_the_handler(self):
        """The card the owner receives and the handler that reads its clicks must agree on the action ids."""
        from app.core.notifications.approval_card import build_approval_card

        decided = set()
        for index in range(2):
            record_id = f"appr-card-{index}"
            await _seed(record_id, action_type="outbound_draft")
            _, components = build_approval_card({"approval_id": record_id, "action_type": "outbound_draft"}, "telegram", "en")

            with patch("app.services.approvals.registry.send_outbound_draft_payload", new_callable=AsyncMock):
                await _host()._handle_action_button_approval(_action_msg(components[0][index].action_id))
            decided.add(await _status_of(record_id))

        assert decided == {"APPROVED", "REJECTED"}
