"""``/draft``: the owner decides on a held reply by typing, where the review request has no buttons.

Decisions run against a real approvals table, so they reach the same funnel the WebUI and the Telegram buttons use;
only the final send to the channel is replaced.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.channels.routing.commands import RouterCommandsDraftMixin, parse_draft_args
from app.channels.types import InboundMessage, OutboundMessage
from app.database.models.approval import ApprovalRecord
from app.services.approvals.registry import ApprovalRegistry
from tests.services.approvals.draft_testkit import draft_payload, held_reply

_DRAFT_ID = "3f9a1c2e5b7d4a6f8c0e1b2d3a4f5e6d"
_SeedDraft = Callable[..., Awaitable[None]]


@pytest_asyncio.fixture
async def seed(tmp_path: Path) -> AsyncIterator[_SeedDraft]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'approvals.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        async with factory() as db:
            yield db

    async def seed_record(record_id: str = _DRAFT_ID, *, status: str = "PENDING", action_type: str = "outbound_draft") -> None:
        async with factory() as db:
            db.add(
                ApprovalRecord(
                    id=record_id,
                    agent_id="agent-1",
                    chat_id="chat-1",
                    thread_id=None,
                    action_type=action_type,
                    reason="test",
                    severity="info",
                    payload=draft_payload(held_reply()),
                    status=status,
                )
            )
            await db.commit()

    async with engine.begin() as conn:
        await conn.run_sync(ApprovalRecord.__table__.create)
    with patch("app.services.approvals.registry.get_session", session):
        yield seed_record
    await engine.dispose()


@pytest.fixture
def send() -> Iterator[AsyncMock]:
    with patch("app.services.approvals.outbound_draft.send_outbound_draft_payload", new_callable=AsyncMock) as sent:
        yield sent


@dataclass
class _Host(RouterCommandsDraftMixin):
    _bus: MagicMock = field(default_factory=MagicMock)

    def __post_init__(self) -> None:
        self._bus.publish_outbound = AsyncMock()

    @property
    def reply(self) -> OutboundMessage:
        self._bus.publish_outbound.assert_awaited_once()
        return self._bus.publish_outbound.await_args.args[0]


def _msg(*, is_group: bool = False, locale: str | None = None) -> InboundMessage:
    return InboundMessage(
        channel="whatsapp",
        sender_id="owner-1",
        chat_id="chat-1",
        content="/draft",
        is_group=is_group,
        message_id="m-7",
        metadata={"locale": locale} if locale else {},
    )


async def _status(record_id: str = _DRAFT_ID) -> str:
    record = await ApprovalRegistry.get_approval(record_id)
    assert record is not None
    return record.status


class TestParseDraftArgs:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("approve 3f9a1c2e", ("approve", "3f9a1c2e")),
            ("reject 3f9a1c2e", ("reject", "3f9a1c2e")),
            ("deny 3f9a1c2e", ("reject", "3f9a1c2e")),
            ("  APPROVE   3F9A1C2E ", ("approve", "3f9a1c2e")),
            ("approve 3f9a1c", ("approve", "3f9a1c")),
            (f"approve {_DRAFT_ID}", ("approve", _DRAFT_ID)),
        ],
    )
    def test_a_decision_and_a_code_are_read(self, raw: str, expected: tuple[str, str]) -> None:
        assert parse_draft_args(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "approve",
            "3f9a1c2e",
            "approve 3f9a1",
            "approve 3f9a1c2e now",
            "send 3f9a1c2e",
            "approve zzzzzzzz",
            "approve 3f9a-1c2e",
        ],
        ids=["empty", "no-code", "no-verb", "short-code", "trailing-words", "unknown-verb", "not-hex", "dash"],
    )
    def test_anything_else_asks_for_the_usage(self, raw: str) -> None:
        assert parse_draft_args(raw) == ("usage", "")


class TestDecidingFromChat:
    @pytest.mark.asyncio
    async def test_approving_sends_the_held_reply(self, seed: _SeedDraft, send: AsyncMock) -> None:
        await seed()
        host = _Host()

        await host._handle_draft_command(_msg(), "approve 3f9a1c2e")

        send.assert_awaited_once()
        assert await _status() == "APPROVED"
        assert host.reply.content == "✅ Reply `3f9a1c2e` approved. It is being sent."

    @pytest.mark.asyncio
    async def test_rejecting_discards_it_unsent(self, seed: _SeedDraft, send: AsyncMock) -> None:
        await seed()
        host = _Host()

        await host._handle_draft_command(_msg(), "reject 3f9a1c2e")

        send.assert_not_awaited()
        assert await _status() == "REJECTED"
        assert host.reply.content == "❌ Reply `3f9a1c2e` rejected. Nothing was sent."

    @pytest.mark.asyncio
    async def test_a_shorter_code_is_enough_and_the_reply_names_the_full_short_code(
        self, seed: _SeedDraft, send: AsyncMock
    ) -> None:
        await seed()
        host = _Host()

        await host._handle_draft_command(_msg(), "approve 3f9a1c")

        assert await _status() == "APPROVED"
        assert "`3f9a1c2e`" in host.reply.content

    @pytest.mark.asyncio
    async def test_the_answer_is_written_in_the_owners_language(self, seed: _SeedDraft, send: AsyncMock) -> None:
        await seed()
        host = _Host()

        await host._handle_draft_command(_msg(locale="zh-CN"), "approve 3f9a1c2e")

        assert host.reply.content == "✅ 回复 `3f9a1c2e` 已批准，正在发送。"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("is_group", "reply_to"), [(False, None), (True, "m-7")])
    async def test_the_answer_goes_back_to_the_chat_it_was_asked_in(
        self, seed: _SeedDraft, send: AsyncMock, is_group: bool, reply_to: str | None
    ) -> None:
        await seed()
        host = _Host()

        await host._handle_draft_command(_msg(is_group=is_group), "approve 3f9a1c2e")

        assert (host.reply.channel, host.reply.recipient_id, host.reply.reply_to_id) == ("whatsapp", "chat-1", reply_to)


class TestWhatCannotBeDecided:
    @pytest.mark.asyncio
    async def test_an_unknown_code_changes_nothing(self, seed: _SeedDraft, send: AsyncMock) -> None:
        await seed()
        host = _Host()

        await host._handle_draft_command(_msg(), "approve abcdef12")

        send.assert_not_awaited()
        assert await _status() == "PENDING"
        assert host.reply.content == "ℹ No reply awaiting review matches `abcdef12`. It may already have been handled."

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", ["APPROVED", "REJECTED", "TIMEOUT"])
    async def test_a_reply_that_is_already_decided_is_not_decided_again(
        self, seed: _SeedDraft, send: AsyncMock, status: str
    ) -> None:
        await seed(status=status)
        host = _Host()

        await host._handle_draft_command(_msg(), "approve 3f9a1c2e")

        send.assert_not_awaited()
        assert await _status() == status
        assert host.reply.content.startswith("ℹ No reply awaiting review matches")

    @pytest.mark.asyncio
    async def test_no_other_kind_of_approval_can_be_decided_with_a_draft_code(self, seed: _SeedDraft, send: AsyncMock) -> None:
        await seed(action_type="shell_command")
        host = _Host()

        await host._handle_draft_command(_msg(), "approve 3f9a1c2e")

        send.assert_not_awaited()
        assert await _status() == "PENDING"
        assert host.reply.content.startswith("ℹ No reply awaiting review matches")

    @pytest.mark.asyncio
    async def test_a_code_shared_by_two_replies_decides_neither(self, seed: _SeedDraft, send: AsyncMock) -> None:
        await seed("7e11aa00" + "c" * 24)
        await seed("7e11aa00" + "d" * 24)
        host = _Host()

        await host._handle_draft_command(_msg(), "approve 7e11aa00")

        send.assert_not_awaited()
        assert await _status("7e11aa00" + "c" * 24) == await _status("7e11aa00" + "d" * 24) == "PENDING"
        assert host.reply.content == "ℹ More than one reply awaiting review matches `7e11aa00`. Send more characters of the code."

    @pytest.mark.asyncio
    @pytest.mark.parametrize("args", ["", "approve", "approve 3f9a", "approve 3f9a1c2e please"])
    async def test_a_malformed_request_gets_the_usage_and_changes_nothing(
        self, seed: _SeedDraft, send: AsyncMock, args: str
    ) -> None:
        await seed()
        host = _Host()

        await host._handle_draft_command(_msg(), args)

        send.assert_not_awaited()
        assert await _status() == "PENDING"
        assert host.reply.content.startswith("Usage: `/draft approve <code>` or `/draft reject <code>`")

    @pytest.mark.asyncio
    async def test_a_failing_lookup_is_reported_and_never_escapes(self, send: AsyncMock) -> None:
        host = _Host()

        with patch.object(ApprovalRegistry, "find_pending_outbound_drafts", AsyncMock(side_effect=RuntimeError("db down"))):
            await host._handle_draft_command(_msg(), "approve 3f9a1c2e")

        assert host.reply.content == "❌ Could not process that. Please try again."
