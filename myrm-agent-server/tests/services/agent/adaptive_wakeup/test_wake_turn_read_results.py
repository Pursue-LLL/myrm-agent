"""A wake turn does not start for results the agent already read in its own turn.

The real scheduler, gateway, service and handler; the stand-ins are the chat store, the event bus, the budget and the
turn the wake would stream.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.agent.coordination.adaptive_wakeup import WakeupEvent, WakeupSourceType
from myrm_agent_harness.agent.meta_tools.spawn_subagent.agent_manage_tool import create_subagent_control_tool
from myrm_agent_harness.agent.sub_agents.types import SubAgentStatus
from myrm_agent_harness.utils.runtime.wakeup_registry import set_global_wakeup_handler

from app.services.agent.adaptive_wakeup import get_adaptive_wakeup_service, wake_turn_scheduler
from app.services.agent.adaptive_wakeup import service as service_module
from app.services.agent.gateway import get_agent_gateway
from app.services.agent.params.workspace_resolve import chat_session_id
from app.services.agent.wakeup_handler import ServerWakeupHandler


@pytest.fixture
def chat_id() -> Iterator[str]:
    chat = f"read-{uuid.uuid4().hex[:8]}"
    yield chat
    get_agent_gateway().release_session(chat)
    wake_turn_scheduler._waiting.pop(chat, None)
    get_adaptive_wakeup_service().forget_chat(chat)


@pytest.fixture(autouse=True)
def quiet_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wake_turn_scheduler, "_POLL_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr("app.services.chat.chat_service.ChatService.get_chat_metadata", AsyncMock(return_value=MagicMock()))
    monkeypatch.setattr("app.services.chat.chat_service.ChatService.ensure_chat_and_append_user_message", AsyncMock())
    monkeypatch.setattr(service_module, "get_event_bus", lambda: MagicMock())
    monkeypatch.setattr(service_module, "check_estop", lambda: None)
    monkeypatch.setattr(service_module, "should_block_execution", AsyncMock(return_value=False))
    registry = MagicMock()
    registry.kill_session_jobs = AsyncMock(return_value=0)
    monkeypatch.setattr("myrm_agent_harness.api.hooks.get_background_registry", lambda: registry)


@pytest.fixture
def streamed(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    stream = AsyncMock(return_value=None)
    monkeypatch.setattr(service_module, "stream_wake_turn", stream)
    return stream


def settlement(chat_id: str, task_id: str) -> WakeupEvent:
    return WakeupEvent(
        source_type=WakeupSourceType.SUBAGENT,
        source_id=task_id,
        session_id=chat_id,
        success=True,
        summary="Subagent 'researcher' completed successfully",
    )


async def settle() -> None:
    async with asyncio.timeout(5):
        while wake_turn_scheduler._tasks:
            await asyncio.gather(*list(wake_turn_scheduler._tasks))


@pytest.mark.asyncio
async def test_results_the_agent_read_while_its_turn_ran_are_not_delivered_again(chat_id: str, streamed: AsyncMock) -> None:
    service = get_adaptive_wakeup_service()
    get_agent_gateway().reserve_session(chat_id, active_message_id="user-turn")

    await service.handle_settlement(settlement(chat_id, "task-1"))
    # The agent's own turn lists its subagents and receives the result.
    ServerWakeupHandler().on_results_read(["task-1"], chat_session_id(chat_id))
    get_agent_gateway().release_session(chat_id)
    await settle()

    streamed.assert_not_awaited()
    # A turn that does not start does not use up the wake budget.
    assert service.get_budget_state(chat_id).consecutive_wakes == 0


@pytest.mark.asyncio
async def test_the_agents_own_list_call_stands_the_queued_wake_down(chat_id: str, streamed: AsyncMock) -> None:
    """From the tool the model calls, through the harness registry and the server handler, to the skipped wake."""
    parent = MagicMock()
    parent.list_children.return_value = [
        {"task_id": "task-1", "status": SubAgentStatus.COMPLETED.value, "result": "found it"},
    ]
    parent._last_context = {"session_id": chat_session_id(chat_id)}
    set_global_wakeup_handler(ServerWakeupHandler())
    try:
        get_agent_gateway().reserve_session(chat_id, active_message_id="user-turn")
        await get_adaptive_wakeup_service().handle_settlement(settlement(chat_id, "task-1"))

        await create_subagent_control_tool(parent).ainvoke({"action": "list"})
        get_agent_gateway().release_session(chat_id)
        await settle()
    finally:
        set_global_wakeup_handler(None)

    streamed.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_agents_own_wait_on_a_settled_child_stands_the_queued_wake_down(chat_id: str, streamed: AsyncMock) -> None:
    """The child settled before the agent waited for it, so its settlement queued a wake the wait's result makes pointless."""
    parent = MagicMock()
    parent.wait_children = AsyncMock(
        return_value={"results": [{"task_id": "task-1", "status": SubAgentStatus.COMPLETED.value}], "failures": []}
    )
    parent._last_context = {"session_id": chat_session_id(chat_id)}
    set_global_wakeup_handler(ServerWakeupHandler())
    try:
        get_agent_gateway().reserve_session(chat_id, active_message_id="user-turn")
        await get_adaptive_wakeup_service().handle_settlement(settlement(chat_id, "task-1"))

        await create_subagent_control_tool(parent).ainvoke({"action": "wait", "task_id": "task-1"})
        get_agent_gateway().release_session(chat_id)
        await settle()
    finally:
        set_global_wakeup_handler(None)

    streamed.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_result_the_agent_did_not_read_is_still_delivered(chat_id: str, streamed: AsyncMock) -> None:
    service = get_adaptive_wakeup_service()
    get_agent_gateway().reserve_session(chat_id, active_message_id="user-turn")

    await service.handle_settlement(settlement(chat_id, "task-1"))
    await service.handle_settlement(settlement(chat_id, "task-2"))
    ServerWakeupHandler().on_results_read(["task-1"], chat_session_id(chat_id))
    get_agent_gateway().release_session(chat_id)
    await settle()

    streamed.assert_awaited_once()
    assert service.get_budget_state(chat_id).consecutive_wakes == 1


@pytest.mark.asyncio
async def test_a_read_that_lands_before_the_settlement_is_routed_still_stands_the_wake_down(
    chat_id: str, streamed: AsyncMock
) -> None:
    ServerWakeupHandler().on_results_read(["task-1"], chat_session_id(chat_id))

    await get_adaptive_wakeup_service().handle_settlement(settlement(chat_id, "task-1"))
    await settle()

    streamed.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_result_read_once_does_not_silence_the_next_settlement(chat_id: str, streamed: AsyncMock) -> None:
    service = get_adaptive_wakeup_service()

    await service.handle_settlement(settlement(chat_id, "task-1"))
    ServerWakeupHandler().on_results_read(["task-1"], chat_session_id(chat_id))
    await settle()
    streamed.assert_not_awaited()

    await service.handle_settlement(settlement(chat_id, "task-2"))
    await settle()

    streamed.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_read_without_a_session_is_ignored(chat_id: str, streamed: AsyncMock) -> None:
    await get_adaptive_wakeup_service().handle_settlement(settlement(chat_id, "task-1"))

    ServerWakeupHandler().on_results_read(["task-1"], None)
    await settle()

    streamed.assert_awaited_once()
