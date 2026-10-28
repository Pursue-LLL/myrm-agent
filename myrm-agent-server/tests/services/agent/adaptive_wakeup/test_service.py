"""What a settled background task does to its chat: a notice row always, a wake turn only when it should.

Checked against the real router and wake budget; only the chat store, the event bus and the wake scheduler are
stand-ins.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.agent.coordination.adaptive_wakeup import WakeupChannel, WakeupEvent, WakeupSourceType

from app.services.agent.adaptive_wakeup import get_adaptive_wakeup_service
from app.services.agent.adaptive_wakeup import service as service_module
from app.services.chat.chat_helpers import WAKEUP_MESSAGE_ID_PREFIX


@pytest.fixture
def chat_id() -> Iterator[str]:
    chat = f"settle-{uuid.uuid4().hex[:8]}"
    yield chat
    get_adaptive_wakeup_service().reset_session(chat)


@pytest.fixture
def append_row(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    append = AsyncMock()
    monkeypatch.setattr("app.services.chat.chat_service.ChatService.ensure_chat_and_append_user_message", append)
    return append


@pytest.fixture
def scheduled(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    schedule = MagicMock(return_value=True)
    monkeypatch.setattr(service_module, "schedule_wake_turn", schedule)
    return schedule


@pytest.fixture(autouse=True)
def silent_bus(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "get_event_bus", lambda: MagicMock())


def settlement(chat_id: str, source_id: str) -> WakeupEvent:
    return WakeupEvent(
        source_type=WakeupSourceType.SUBAGENT,
        source_id=source_id,
        session_id=chat_id,
        success=True,
        summary="Subagent 'researcher' completed successfully",
    )


def appended(append_row: AsyncMock, index: int = -1) -> dict[str, object]:
    return dict(append_row.await_args_list[index].kwargs)


@pytest.mark.asyncio
async def test_a_settlement_with_budget_left_is_noted_in_the_chat_and_wakes_it(
    chat_id: str, append_row: AsyncMock, scheduled: MagicMock
) -> None:
    decision = await get_adaptive_wakeup_service().handle_settlement(settlement(chat_id, "task-1"), agent_id="agent-1")

    assert decision.channel == WakeupChannel.FOLLOWUP
    row = appended(append_row)
    assert row["chat_id"] == chat_id
    assert row["message_id"] == f"{WAKEUP_MESSAGE_ID_PREFIX}followup_task-1_1"
    assert "type='adaptive_wakeup_followup'" in str(row["content"])
    assert "Autonomous wake turn (1/3)" in str(row["content"])
    scheduled.assert_called_once_with(chat_id, "agent-1")


@pytest.mark.asyncio
async def test_a_settlement_past_the_budget_is_noted_in_the_chat_without_waking_it(
    chat_id: str, append_row: AsyncMock, scheduled: MagicMock
) -> None:
    service = get_adaptive_wakeup_service()
    for index in range(3):
        await service.handle_settlement(settlement(chat_id, f"task-{index}"))
    scheduled.reset_mock()

    decision = await service.handle_settlement(settlement(chat_id, "task-3"))

    assert decision.channel == WakeupChannel.DEGRADE
    row = appended(append_row)
    assert row["message_id"] == f"{WAKEUP_MESSAGE_ID_PREFIX}degraded_task-3"
    assert "reached consecutive wake limit (3)" in str(row["content"])
    scheduled.assert_not_called()


@pytest.mark.asyncio
async def test_a_settlement_after_a_stop_is_noted_in_the_chat_without_waking_it(
    chat_id: str, append_row: AsyncMock, scheduled: MagicMock
) -> None:
    service = get_adaptive_wakeup_service()
    service.record_user_stop(chat_id)

    decision = await service.handle_settlement(settlement(chat_id, "task-1"))

    assert decision.channel == WakeupChannel.SUPPRESS
    # The result must not be lost: the next message the user writes finds it in the history.
    row = appended(append_row)
    assert row["message_id"] == f"{WAKEUP_MESSAGE_ID_PREFIX}suppressed_task-1"
    assert "type='adaptive_settlement_suppressed'" in str(row["content"])
    assert "the user stopped this session" in str(row["content"])
    scheduled.assert_not_called()
    assert service.get_budget_state(chat_id).consecutive_wakes == 0


@pytest.mark.asyncio
async def test_the_next_message_the_user_writes_lifts_the_stop_and_restores_the_budget(
    chat_id: str, append_row: AsyncMock, scheduled: MagicMock
) -> None:
    service = get_adaptive_wakeup_service()
    for index in range(3):
        await service.handle_settlement(settlement(chat_id, f"task-{index}"))
    service.record_user_stop(chat_id)

    service.record_human_turn(chat_id)
    decision = await service.handle_settlement(settlement(chat_id, "task-after"))

    assert decision.channel == WakeupChannel.FOLLOWUP
    assert decision.consecutive_wakes == 1
