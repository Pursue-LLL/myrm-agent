"""Replays of one chat reach one turn that acknowledges every journal entry it consumed.

The session gate merges what it holds for a chat into one turn, and the replays a restart submits arrive back to back in
one debounce window. The turn must therefore carry the entry of every replay it merged: an entry left behind would be
replayed again at the next restart inside its lifetime, a message the agent has already answered.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.channels.core.gateway import ChannelGateway
from app.channels.reliability.inbound_journal import (
    SqliteInboundJournal,
    create_journal_entry_from_inbound,
    is_recovered,
    recovered_entry_ids,
    restore_inbound,
)
from app.channels.routing.session_gate import SessionGate, SessionGateConfig
from app.channels.types import InboundMessage
from tests.channels.routing.pipeline.turn_pipeline_testkit import prepared_message, turn_router


def _dm(text: str) -> InboundMessage:
    return InboundMessage(channel="telegram", sender_id="u1", chat_id="u1", content=text)


def _replayed(text: str) -> InboundMessage:
    return restore_inbound(create_journal_entry_from_inbound(_dm(text)))


class _Host:
    """What the router does with the gate: records each turn it is handed."""

    def __init__(self) -> None:
        self.turns: list[InboundMessage] = []
        self.gate = SessionGate(SessionGateConfig(debounce_window_ms=30), on_ready=self._run)

    async def _run(self, msg: InboundMessage) -> None:
        self.turns.append(msg)


async def _until(condition: Callable[[], bool], *, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        await asyncio.sleep(0.02)


async def test_every_entry_of_merged_replays_is_acknowledged_when_the_turn_is_over(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = SqliteInboundJournal(db_path=tmp_path / "journal.db")
    for text in ("one", "two"):
        journal.write(create_journal_entry_from_inbound(_dm(text)))
    router = turn_router()
    router._gate = SessionGate(SessionGateConfig(debounce_window_ms=30), on_ready=router._handle_merged)
    monkeypatch.setattr(router, "_enrich_attachments", AsyncMock(side_effect=lambda inbound, **_: inbound))
    router.set_inbound_journal(journal)
    gateway = ChannelGateway(inbound_journal=journal)
    gateway._router = router

    await gateway._recover_journal()
    await _until(lambda: not journal.scan_pending())

    assert prepared_message(router).content == "one\ntwo"
    assert journal.scan_pending() == []


async def test_replays_of_one_chat_run_as_one_turn_that_names_every_entry() -> None:
    first, second = _replayed("one"), _replayed("two")
    host = _Host()

    host.gate.submit(first)
    host.gate.submit(second)
    await _until(lambda: bool(host.turns))

    [turn] = host.turns
    assert turn.content == "one\ntwo"
    assert is_recovered(turn)
    assert recovered_entry_ids(turn) == recovered_entry_ids(first) + recovered_entry_ids(second)
    assert len(recovered_entry_ids(turn)) == 2


@pytest.mark.parametrize("replay_first", [True, False])
async def test_a_replay_and_a_live_message_take_separate_turns_in_arrival_order(replay_first: bool) -> None:
    replay, live = _replayed("old"), _dm("new")
    arrivals = (replay, live) if replay_first else (live, replay)
    host = _Host()

    for message in arrivals:
        host.gate.submit(message)
    await _until(lambda: len(host.turns) == 2)

    assert [(turn.content, is_recovered(turn), recovered_entry_ids(turn)) for turn in host.turns] == [
        (message.content, is_recovered(message), recovered_entry_ids(message)) for message in arrivals
    ]
