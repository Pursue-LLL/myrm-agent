"""History sync against the real chat tables: when does the agent thread still mirror the stored conversation."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select, update

from app.database.models.chat import Chat, Message
from app.database.repositories.chat_history_sync_repo import ChatHistorySyncRepository, ConversationBranch
from app.platform_utils import get_session_factory
from app.services.chat.history_sync import commit_history_sync, decide_history_mode, history_digest

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


class _Chat:
    """A stored chat with helpers that write rows the way the chat services do."""

    def __init__(self, chat_id: str) -> None:
        self.chat_id = chat_id
        self._clock = 0

    @classmethod
    async def create(cls) -> _Chat:
        chat = cls(f"sync-{uuid.uuid4().hex[:10]}")
        async with get_session_factory()() as db:
            db.add(Chat(id=chat.chat_id, title="history sync"))
            await db.commit()
        return chat

    async def add(
        self,
        role: str,
        *,
        request_message_id: str | None = None,
        same_instant_as_previous: bool = False,
    ) -> str:
        message_id = str(uuid.uuid4())
        if not same_instant_as_previous:
            self._clock += 1
        stamp = _BASE_TIME + timedelta(seconds=self._clock)
        extra = {"request_message_id": request_message_id} if request_message_id else None
        async with get_session_factory()() as db:
            db.add(
                Message(
                    id=message_id,
                    chat_id=self.chat_id,
                    role=role,
                    content=f"{role}-{message_id[:6]}",
                    sent_at=stamp,
                    sent_timezone="UTC",
                    created_at=stamp,
                    extra_data=extra,
                )
            )
            await db.commit()
        return message_id

    async def exchange(self, request_id: str) -> tuple[str, str]:
        return await self.add("user"), await self.add("assistant", request_message_id=request_id)

    async def update_messages(self, message_id: str, **values: object) -> None:
        async with get_session_factory()() as db:
            await db.execute(update(Message).where(Message.id == message_id).values(**values))
            await db.commit()

    async def delete_message(self, message_id: str) -> None:
        async with get_session_factory()() as db:
            await db.execute(delete(Message).where(Message.id == message_id))
            await db.commit()

    async def chat_row(self) -> Chat:
        async with get_session_factory()() as db:
            return (await db.execute(select(Chat).where(Chat.id == self.chat_id))).scalar_one()

    async def stored_token(self) -> str | None:
        return (await self.chat_row()).history_sync_token


@pytest.fixture
async def chat() -> _Chat:
    return await _Chat.create()


def _branch(*ids: str, summary: str | None = None, before_id: str | None = None) -> ConversationBranch:
    return ConversationBranch(
        stored_token=None,
        compacted_summary=summary,
        compacted_before_id=before_id,
        message_ids=ids,
    )


class TestHistoryDigest:
    def test_the_order_of_messages_matters(self) -> None:
        assert history_digest(_branch("a", "b")) != history_digest(_branch("b", "a"))

    def test_the_boundary_between_ids_is_not_ambiguous(self) -> None:
        assert history_digest(_branch("ab", "c")) != history_digest(_branch("a", "bc"))

    def test_a_compaction_changes_the_digest_even_when_no_message_id_does(self) -> None:
        assert history_digest(_branch("a")) != history_digest(_branch("a", summary="s", before_id="a"))
        assert history_digest(_branch("a", summary="one", before_id="a")) != history_digest(
            _branch("a", summary="two", before_id="a")
        )

    def test_the_stored_token_is_not_part_of_the_digest(self) -> None:
        stored = _branch("a")._replace(stored_token="anything")
        assert history_digest(stored) == history_digest(_branch("a"))


@pytest.mark.asyncio
async def test_a_chat_that_does_not_exist_rebuilds_the_thread() -> None:
    assert await decide_history_mode("no-such-chat", exclude_message_id=None) == "replace"


@pytest.mark.asyncio
async def test_a_chat_without_a_record_rebuilds_the_thread(chat: _Chat) -> None:
    """New, upgraded and forked chats have no record, so their first turn is cold."""
    await chat.exchange("r1")

    assert await decide_history_mode(chat.chat_id, exclude_message_id=None) == "replace"


@pytest.mark.asyncio
async def test_a_completed_turn_lets_the_next_turn_continue(chat: _Chat) -> None:
    await chat.exchange("r1")
    assert await commit_history_sync(chat.chat_id, "r1") is True

    next_user = await chat.add("user")

    assert await decide_history_mode(chat.chat_id, exclude_message_id=next_user) == "continue"


@pytest.mark.asyncio
async def test_the_turns_own_user_message_is_input_and_not_part_of_the_comparison(chat: _Chat) -> None:
    await chat.exchange("r1")
    await commit_history_sync(chat.chat_id, "r1")
    next_user = await chat.add("user")

    assert await decide_history_mode(chat.chat_id, exclude_message_id=None) == "replace"
    assert await decide_history_mode(chat.chat_id, exclude_message_id=next_user) == "continue"


@pytest.mark.asyncio
async def test_a_turn_whose_answer_was_not_stored_records_nothing(chat: _Chat) -> None:
    await chat.exchange("r1")
    await commit_history_sync(chat.chat_id, "r1")
    recorded = await chat.stored_token()
    await chat.add("user")

    assert await commit_history_sync(chat.chat_id, "r2") is False

    assert await chat.stored_token() == recorded
    assert await decide_history_mode(chat.chat_id, exclude_message_id=None) == "replace"


@pytest.mark.asyncio
async def test_an_answer_that_is_no_longer_active_is_not_the_turns_answer(chat: _Chat) -> None:
    _, answer = await chat.exchange("r1")
    await chat.update_messages(answer, is_active=False)

    assert await commit_history_sync(chat.chat_id, "r1") is False
    assert await chat.stored_token() is None


@pytest.mark.asyncio
async def test_another_requests_answer_does_not_stand_in_for_this_turns(chat: _Chat) -> None:
    await chat.exchange("r1")

    assert await commit_history_sync(chat.chat_id, "r2") is False


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda chat, ids: chat.delete_message(ids["a2"]), id="undo-drops-the-last-answer"),
        pytest.param(lambda chat, ids: chat.add("assistant"), id="server-appended-notice"),
        pytest.param(lambda chat, ids: chat.update_messages(ids["a2"], is_active=False), id="regenerate-deactivates"),
        pytest.param(lambda chat, ids: chat.delete_message(ids["u1"]), id="earlier-message-removed"),
    ],
)
@pytest.mark.asyncio
async def test_any_change_the_thread_did_not_witness_rebuilds_it(
    chat: _Chat,
    mutate: Callable[[_Chat, dict[str, str]], Awaitable[object]],
) -> None:
    u1, a1 = await chat.exchange("r1")
    u2, a2 = await chat.exchange("r2")
    await commit_history_sync(chat.chat_id, "r2")
    assert await decide_history_mode(chat.chat_id, exclude_message_id=None) == "continue"

    await mutate(chat, {"u1": u1, "a1": a1, "u2": u2, "a2": a2})

    assert await decide_history_mode(chat.chat_id, exclude_message_id=None) == "replace"


@pytest.mark.asyncio
async def test_switching_to_a_sibling_answer_rebuilds_the_thread(chat: _Chat) -> None:
    await chat.exchange("r1")
    _, shown = await chat.exchange("r2")
    sibling = await chat.add("assistant", request_message_id="r3")
    await chat.update_messages(sibling, is_active=False)
    await commit_history_sync(chat.chat_id, "r2")

    await chat.update_messages(shown, is_active=False)
    await chat.update_messages(sibling, is_active=True)

    assert await decide_history_mode(chat.chat_id, exclude_message_id=None) == "replace"


@pytest.mark.asyncio
async def test_a_compaction_rebuilds_the_thread(chat: _Chat) -> None:
    u1, _ = await chat.exchange("r1")
    await chat.exchange("r2")
    await commit_history_sync(chat.chat_id, "r2")

    async with get_session_factory()() as db:
        await db.execute(update(Chat).where(Chat.id == chat.chat_id).values(compacted_summary="summary", compacted_before_id=u1))
        await db.commit()

    assert await decide_history_mode(chat.chat_id, exclude_message_id=None) == "replace"


@pytest.mark.asyncio
async def test_messages_before_the_compaction_anchor_are_not_part_of_the_comparison(chat: _Chat) -> None:
    """The stored history ends at the anchor, so removing something older must not cost a cold turn."""
    old_user, _ = await chat.exchange("r1")
    anchor_user, _ = await chat.exchange("r2")
    async with get_session_factory()() as db:
        await db.execute(
            update(Chat).where(Chat.id == chat.chat_id).values(compacted_summary="summary", compacted_before_id=anchor_user)
        )
        await db.commit()
    await chat.exchange("r3")
    await commit_history_sync(chat.chat_id, "r3")

    await chat.delete_message(old_user)

    assert await decide_history_mode(chat.chat_id, exclude_message_id=None) == "continue"


@pytest.mark.asyncio
async def test_messages_stamped_with_the_same_instant_keep_one_stable_order(chat: _Chat) -> None:
    await chat.add("user")
    await chat.add("assistant", request_message_id="r1", same_instant_as_previous=True)
    await commit_history_sync(chat.chat_id, "r1")

    for _ in range(3):
        assert await decide_history_mode(chat.chat_id, exclude_message_id=None) == "continue"


@pytest.mark.asyncio
async def test_a_failed_read_rebuilds_the_thread(chat: _Chat, monkeypatch: pytest.MonkeyPatch) -> None:
    await chat.exchange("r1")
    await commit_history_sync(chat.chat_id, "r1")

    async def broken(*_args: object, **_kwargs: object) -> ConversationBranch:
        raise RuntimeError("database is locked")

    monkeypatch.setattr(ChatHistorySyncRepository, "load_branch", staticmethod(broken))

    assert await decide_history_mode(chat.chat_id, exclude_message_id=None) == "replace"


@pytest.mark.asyncio
async def test_a_failed_commit_never_fails_the_turn_and_leaves_the_old_record(
    chat: _Chat,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await chat.exchange("r1")

    async def broken(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("database is locked")

    monkeypatch.setattr(ChatHistorySyncRepository, "store_token", staticmethod(broken))

    assert await commit_history_sync(chat.chat_id, "r1") is False
    assert await chat.stored_token() is None


@pytest.mark.asyncio
async def test_recording_the_token_is_not_chat_activity(chat: _Chat) -> None:
    await chat.exchange("r1")
    before = (await chat.chat_row()).updated_at

    assert await commit_history_sync(chat.chat_id, "r1") is True

    assert (await chat.chat_row()).updated_at == before


@pytest.mark.asyncio
async def test_the_stored_record_is_the_digest_of_the_stored_conversation(chat: _Chat) -> None:
    await chat.exchange("r1")
    await commit_history_sync(chat.chat_id, "r1")

    async with get_session_factory()() as db:
        branch = await ChatHistorySyncRepository.load_branch(db, chat.chat_id)

    assert branch is not None
    assert branch.stored_token == history_digest(branch)
