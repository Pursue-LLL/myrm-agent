"""A stopping router parks the messages that have not started a turn in the inbound journal and starts no further turn.

Runs on a started ``AgentRouter`` (its consume loop and janitor are the awaits during which the cancelled turn unwinds),
the real ``SessionGate`` and a real SQLite journal. The sender of a queued message was told it is queued: the next start
replays it from the journal, and the turn ending under the cancellation of the stop must not pick it up as a new turn on
the way out.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

from app.channels.reliability.inbound_journal import JournalEntry, SqliteInboundJournal
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
        bus = make_bus()
        bus.consume_inbound = _no_inbound
        self.router: AgentRouter = make_router(bus)
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


def _contents(entries: list[JournalEntry]) -> list[str]:
    return [entry.content for entry in entries]


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
    assert {(entry.channel, entry.chat_id, entry.sender_id) for entry in parked} == {("telegram", "chat-1", "u1")}


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
    journal.write(
        JournalEntry(
            id="entry-1",
            channel="telegram",
            chat_id="chat-1",
            sender_id="u1",
            user_id="",
            content="replayed",
            metadata_json="{}",
            media_json="[]",
            thread_id=None,
            is_group=False,
            created_at=time.time(),
        )
    )

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
