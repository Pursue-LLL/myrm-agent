"""When a settled background task's wake turn starts, and what starting it costs.

The real service, router, scheduler and gateway run together; the stand-ins are the part that needs a model (building
the agent and streaming its turn), the chat store, the emergency stop file and the daily budget.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.agent.coordination.adaptive_wakeup import WakeupChannel, WakeupEvent, WakeupSourceType
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

from app.services.agent.adaptive_wakeup import get_adaptive_wakeup_service, wake_turn_scheduler
from app.services.agent.adaptive_wakeup import service as service_module
from app.services.agent.gateway import get_agent_gateway


@pytest.fixture
def chat_id() -> Iterator[str]:
    chat = f"policy-{uuid.uuid4().hex[:8]}"
    yield chat
    get_agent_gateway().release_session(chat)
    wake_turn_scheduler._waiting.pop(chat, None)
    get_adaptive_wakeup_service().forget_chat(chat)


@pytest.fixture(autouse=True)
def quiet_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wake_turn_scheduler, "_POLL_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(service_module, "check_estop", lambda: None)
    monkeypatch.setattr(service_module, "should_block_execution", AsyncMock(return_value=False))
    monkeypatch.setattr(service_module, "get_event_bus", lambda: MagicMock())
    monkeypatch.setattr("app.services.chat.chat_service.ChatService.get_chat_metadata", AsyncMock(return_value=MagicMock()))
    monkeypatch.setattr("app.services.chat.chat_service.ChatService.ensure_chat_and_append_user_message", AsyncMock())
    registry = MagicMock()
    registry.kill_session_jobs = AsyncMock(return_value=0)
    monkeypatch.setattr("myrm_agent_harness.api.hooks.get_background_registry", lambda: registry)


@pytest.fixture
def streamed(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The chats whose wake turn actually streamed."""
    chats: list[str] = []

    async def fake_stream(chat: str, _turn: str, _token: CancellationToken) -> None:
        chats.append(chat)

    monkeypatch.setattr(service_module, "stream_wake_turn", fake_stream)
    return chats


def settlement(chat_id: str, source_id: str = "task-1") -> WakeupEvent:
    return WakeupEvent(
        source_type=WakeupSourceType.SUBAGENT,
        source_id=source_id,
        session_id=chat_id,
        success=True,
        summary="Subagent 'researcher' completed successfully",
    )


async def settle() -> None:
    async with asyncio.timeout(5):
        while wake_turn_scheduler._tasks:
            await asyncio.gather(*list(wake_turn_scheduler._tasks))


@pytest.mark.asyncio
async def test_a_wake_turn_that_starts_spends_one_unit_of_the_budget(chat_id: str, streamed: list[str]) -> None:
    service = get_adaptive_wakeup_service()

    await service.handle_settlement(settlement(chat_id))
    await settle()

    assert streamed == [chat_id]
    assert service.get_budget_state(chat_id).consecutive_wakes == 1


@pytest.mark.asyncio
async def test_settlements_that_share_one_wake_turn_spend_one_unit_between_them(chat_id: str, streamed: list[str]) -> None:
    service = get_adaptive_wakeup_service()
    get_agent_gateway().reserve_session(chat_id, active_message_id="user-turn")

    for index in range(5):
        decision = await service.handle_settlement(settlement(chat_id, f"task-{index}"))
        assert decision is not None
        assert decision.channel == WakeupChannel.FOLLOWUP
    get_agent_gateway().release_session(chat_id)
    await settle()

    assert streamed == [chat_id]
    assert service.get_budget_state(chat_id).consecutive_wakes == 1


@pytest.mark.asyncio
async def test_the_wake_turns_stop_after_the_budget_and_the_next_settlement_is_degraded(
    chat_id: str, streamed: list[str]
) -> None:
    service = get_adaptive_wakeup_service()
    for index in range(3):
        await service.handle_settlement(settlement(chat_id, f"task-{index}"))
        await settle()

    decision = await service.handle_settlement(settlement(chat_id, "task-3"))
    await settle()

    assert streamed == [chat_id] * 3
    assert decision is not None
    assert decision.channel == WakeupChannel.DEGRADE


@pytest.mark.asyncio
async def test_a_stop_while_the_wake_waits_keeps_it_from_running_and_costs_nothing(chat_id: str, streamed: list[str]) -> None:
    service = get_adaptive_wakeup_service()
    gateway = get_agent_gateway()
    gateway.reserve_session(chat_id, active_message_id="user-turn")
    await service.handle_settlement(settlement(chat_id))

    service.record_user_stop(chat_id)
    gateway.release_session(chat_id)
    await settle()

    assert streamed == []
    assert service.get_budget_state(chat_id).consecutive_wakes == 0
    assert not gateway.is_session_active(chat_id)


@pytest.mark.asyncio
async def test_a_message_the_user_wrote_after_the_notice_keeps_the_wake_from_running(chat_id: str, streamed: list[str]) -> None:
    service = get_adaptive_wakeup_service()
    gateway = get_agent_gateway()
    gateway.reserve_session(chat_id, active_message_id="user-turn")
    await service.handle_settlement(settlement(chat_id))

    # The user's own turn read the notice already; waking again would answer it twice.
    service.record_human_turn(chat_id)
    gateway.release_session(chat_id)
    await settle()

    assert streamed == []


@pytest.mark.asyncio
async def test_a_message_the_user_wrote_before_the_notice_does_not_keep_the_wake_from_running(
    chat_id: str, streamed: list[str]
) -> None:
    service = get_adaptive_wakeup_service()
    service.record_human_turn(chat_id)
    await asyncio.sleep(0.01)

    await service.handle_settlement(settlement(chat_id))
    await settle()

    assert streamed == [chat_id]


@pytest.mark.parametrize(
    ("arm", "reason"),
    [
        pytest.param(
            lambda monkeypatch: monkeypatch.setattr(service_module, "check_estop", lambda: object()),
            "emergency stop",
            id="emergency-stop",
        ),
        pytest.param(
            lambda monkeypatch: monkeypatch.setattr(service_module, "should_block_execution", AsyncMock(return_value=True)),
            "daily budget",
            id="daily-budget",
        ),
    ],
)
@pytest.mark.asyncio
async def test_the_wake_does_not_run_while_it_is_forbidden_and_costs_nothing(
    chat_id: str,
    streamed: list[str],
    monkeypatch: pytest.MonkeyPatch,
    arm: Callable[[pytest.MonkeyPatch], None],
    reason: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    arm(monkeypatch)
    service = get_adaptive_wakeup_service()

    with caplog.at_level("INFO", logger=service_module.logger.name):
        await service.handle_settlement(settlement(chat_id))
        await settle()

    assert streamed == []
    assert reason in caplog.text
    assert service.get_budget_state(chat_id).consecutive_wakes == 0
    assert not get_agent_gateway().is_session_active(chat_id)
