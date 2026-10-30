"""A stopping router parks the messages that have not started a turn in the inbound journal and starts no further turn.

Runs on a started ``AgentRouter`` (its consume loop and janitor are the awaits during which the cancelled turn unwinds),
the real ``SessionGate`` and a real SQLite journal. The sender of a queued message was told it is queued: the next start
replays it from the journal, and the turn ending under the cancellation of the stop must not pick it up as a new turn on
the way out. The turn the stop cancels is not replayed, so its chat is told to send the request again; that notice is
sent to all the chats together and a send that never returns does not hold the stop up.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

from app.channels.i18n import channel_t
from app.channels.reliability.inbound_journal import (
    JournalEntry,
    SqliteInboundJournal,
    create_journal_entry_from_inbound,
    restore_inbound,
)
from app.channels.routing.pipeline import lifecycle
from app.channels.routing.router import AgentRouter
from app.channels.routing.router_models import _ActiveTask
from app.channels.routing.session_gate import SessionGate, SessionGateConfig
from app.channels.types import InboundMessage

from ..risk_gate_testkit import make_bus, make_router


def _dm(text: str, **metadata: object) -> InboundMessage:
    return InboundMessage(channel="telegram", sender_id="u1", chat_id="chat-1", content=text, metadata=dict(metadata))


async def _no_inbound() -> InboundMessage:
    await asyncio.sleep(3600)
    raise AssertionError("the consume loop must not receive a message")


class _Harness:
    """A router whose gate hands each turn to a runner; the turn named ``running`` registers like a real run and waits."""

    def __init__(self, journal: SqliteInboundJournal | None) -> None:
        self.ran: list[str] = []
        self.release = asyncio.Event()
        self.bus = make_bus()
        self.bus.consume_inbound = _no_inbound
        self.router: AgentRouter = make_router(self.bus)
        if journal is not None:
            self.router.set_inbound_journal(journal)
        self.router._gate = SessionGate(SessionGateConfig(debounce_window_ms=0), on_ready=self._run)

    async def _run(self, msg: InboundMessage) -> None:
        self.ran.append(msg.content)
        if msg.content != "running":
            return
        task = asyncio.current_task()
        assert task is not None
        self.router._active_tasks["telegram:chat-1"] = _ActiveTask(
            task=task,
            cancel_token=MagicMock(spec=CancellationToken),
            channel="telegram",
            chat_id="chat-1",
            placeholder_id=None,
            started_at=time.monotonic(),
        )
        await self.release.wait()

    async def start(self) -> None:
        await self.router.start()

    async def start_running_turn_with_queue(self, *queued: InboundMessage) -> None:
        self.router._gate.submit(_dm("running"))
        await asyncio.sleep(0.05)
        for msg in queued:
            self.router._gate.submit(msg)
        await asyncio.sleep(0.05)
        assert self.ran == ["running"]


@pytest.fixture
def journal(tmp_path: Path) -> SqliteInboundJournal:
    return SqliteInboundJournal(tmp_path / "journal.db")


@pytest.fixture
async def harness(journal: SqliteInboundJournal) -> AsyncIterator[_Harness]:
    made = _Harness(journal)
    await made.start()
    yield made
    made.release.set()
    await asyncio.sleep(0.05)


def _replays(entries: list[JournalEntry]) -> list[InboundMessage]:
    return [restore_inbound(entry) for entry in entries]


def _contents(entries: list[JournalEntry]) -> list[str]:
    return [msg.content for msg in _replays(entries)]


@pytest.mark.asyncio
async def test_queued_messages_are_in_the_journal_in_arrival_order_after_a_stop(
    harness: _Harness, journal: SqliteInboundJournal
) -> None:
    await harness.start_running_turn_with_queue(_dm("queued-1"), _dm("queued-2"))
    assert journal.scan_pending() == []

    await harness.router.stop()
    await asyncio.sleep(0.1)

    parked = journal.scan_pending()
    assert _contents(parked) == ["queued-1", "queued-2"]
    assert {(msg.channel, msg.chat_id, msg.sender_id) for msg in _replays(parked)} == {("telegram", "chat-1", "u1")}


@pytest.mark.asyncio
async def test_the_turn_ended_by_the_stop_does_not_start_the_next_queued_one(harness: _Harness) -> None:
    await harness.start_running_turn_with_queue(_dm("queued"))

    await harness.router.stop()
    await asyncio.sleep(0.1)

    assert harness.ran == ["running"]


@pytest.mark.asyncio
async def test_a_stop_without_a_journal_still_starts_no_further_turn() -> None:
    harness = _Harness(None)
    await harness.start()
    await harness.start_running_turn_with_queue(_dm("queued"))

    await harness.router.stop()
    await asyncio.sleep(0.1)
    harness.release.set()

    assert harness.ran == ["running"]


@pytest.mark.asyncio
async def test_a_replayed_message_keeps_its_entry_and_is_not_written_twice(
    harness: _Harness, journal: SqliteInboundJournal
) -> None:
    replay = _dm("replayed", is_recovery=True, recovery_entry_id="entry-1")
    await harness.start_running_turn_with_queue(replay)
    journal.write(replace(create_journal_entry_from_inbound(_dm("replayed")), id="entry-1"))

    await harness.router.stop()

    assert [parked.id for parked in journal.scan_pending()] == ["entry-1"]


@pytest.mark.asyncio
async def test_an_answer_to_a_tool_approval_is_not_parked(harness: _Harness, journal: SqliteInboundJournal) -> None:
    answer = InboundMessage(
        channel="telegram",
        sender_id="u1",
        chat_id="chat-1",
        content="approve",
        resume_value={"decisions": [{"type": "approve"}]},
    )
    await harness.start_running_turn_with_queue(answer, _dm("queued"))

    await harness.router.stop()

    assert _contents(journal.scan_pending()) == ["queued"]


@pytest.mark.asyncio
async def test_the_chat_of_a_turn_the_stop_cancels_is_told_to_send_the_request_again(harness: _Harness) -> None:
    await harness.start_running_turn_with_queue()

    await harness.router.stop()

    notice = channel_t("en", "turn_interrupted_by_restart")
    assert notice != "turn_interrupted_by_restart"
    sent = [call.args[0] for call in harness.bus.publish_outbound.await_args_list]
    assert [(msg.channel, msg.recipient_id, msg.content) for msg in sent] == [("telegram", "chat-1", notice)]


@pytest.mark.asyncio
async def test_a_stop_with_no_turn_running_sends_no_notice(harness: _Harness) -> None:
    await harness.router.stop()

    harness.bus.publish_outbound.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_turn_that_shows_a_placeholder_has_it_replaced_by_the_notice(harness: _Harness) -> None:
    await harness.start_running_turn_with_queue()
    harness.router._active_tasks["telegram:chat-1"].placeholder_id = "ph-1"

    with patch.object(harness.router._fx, "cleanup_placeholder", new=AsyncMock()) as cleanup:
        await harness.router.stop()

    cleanup.assert_awaited_once_with("telegram", "chat-1", "ph-1", channel_t("en", "turn_interrupted_by_restart"))
    harness.bus.publish_outbound.assert_not_awaited()


def _register_running_turn(harness: _Harness, chat_id: str, placeholder_id: str | None) -> asyncio.Task[None]:
    task = asyncio.create_task(asyncio.sleep(3600))
    harness.router._active_tasks[f"telegram:{chat_id}"] = _ActiveTask(
        task=task,
        cancel_token=MagicMock(spec=CancellationToken),
        channel="telegram",
        chat_id=chat_id,
        placeholder_id=placeholder_id,
        started_at=time.monotonic(),
    )
    return task


@pytest.mark.asyncio
async def test_a_notice_whose_send_never_returns_does_not_hold_the_stop_up(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(lifecycle, "_NOTICE_SEND_TIMEOUT", 0.2)
    _register_running_turn(harness, "chat-1", "ph-1")

    async def never_returns(*_args: object) -> None:
        await asyncio.sleep(3600)

    with patch.object(harness.router._fx, "cleanup_placeholder", new=never_returns):
        await asyncio.wait_for(harness.router.stop(), timeout=2.0)

    assert harness.router._active_tasks == {}


@pytest.mark.asyncio
async def test_the_chats_of_all_cancelled_turns_are_told_together(harness: _Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    """Each send waits for all of them to have started: sent one after another, none could finish."""
    monkeypatch.setattr(lifecycle, "_NOTICE_SEND_TIMEOUT", 0.5)
    placeholders = ["ph-1", "ph-2", "ph-3"]
    for index, placeholder_id in enumerate(placeholders, start=1):
        _register_running_turn(harness, f"chat-{index}", placeholder_id)
    started: list[str] = []
    all_started = asyncio.Event()
    told: list[str] = []

    async def cleanup(_channel: str, _chat_id: str, placeholder_id: str, _text: str) -> None:
        started.append(placeholder_id)
        if len(started) == len(placeholders):
            all_started.set()
        await all_started.wait()
        told.append(placeholder_id)

    with patch.object(harness.router._fx, "cleanup_placeholder", new=cleanup):
        await harness.router.stop()

    assert sorted(told) == placeholders
