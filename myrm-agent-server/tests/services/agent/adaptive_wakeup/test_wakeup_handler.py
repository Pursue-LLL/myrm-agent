"""A finished background subagent is settled into the chat that started it, not under the harness's session key."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.agent.coordination.adaptive_wakeup import WakeupEvent, WakeupSourceType
from myrm_agent_harness.agent.sub_agents.types import SubAgentResult

from app.services.agent import wakeup_handler
from app.services.agent.params.workspace_resolve import chat_id_from_session_id, chat_session_id
from app.services.agent.wakeup_handler import ServerWakeupHandler


@pytest.mark.parametrize("chat_id", ["abc-uuid-1", "chat_codex_import_7", "chat_chat_x", ""])
def test_the_session_key_of_a_chat_maps_back_to_the_chat(chat_id: str) -> None:
    assert chat_id_from_session_id(chat_session_id(chat_id)) == chat_id


async def settled_event(monkeypatch: pytest.MonkeyPatch, session_id: str | None) -> list[WakeupEvent]:
    events: list[WakeupEvent] = []
    service = MagicMock()
    service.handle_settlement = AsyncMock(side_effect=events.append)
    monkeypatch.setattr(wakeup_handler, "get_adaptive_wakeup_service", lambda: service)
    result = SubAgentResult(task_id="task-1", agent_type="researcher", success=True, result="done", duration_seconds=1.5)

    await ServerWakeupHandler().on_async_wakeup(result, "planner", session_id)
    while wakeup_handler._tasks:
        await asyncio.gather(*list(wakeup_handler._tasks))
    return events


@pytest.mark.asyncio
async def test_a_subagent_started_by_a_chat_run_settles_into_that_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    events = await settled_event(monkeypatch, chat_session_id("abc-uuid-1"))

    assert len(events) == 1
    assert events[0].session_id == "abc-uuid-1"
    assert events[0].source_type == WakeupSourceType.SUBAGENT
    assert events[0].source_id == "task-1"
    assert events[0].summary == "Subagent 'researcher' completed successfully"


@pytest.mark.asyncio
async def test_a_subagent_without_a_session_settles_nowhere(monkeypatch: pytest.MonkeyPatch) -> None:
    assert await settled_event(monkeypatch, None) == []


@pytest.mark.asyncio
async def test_a_failing_settlement_does_not_escape_the_detached_task(monkeypatch: pytest.MonkeyPatch) -> None:
    service = MagicMock()
    service.handle_settlement = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(wakeup_handler, "get_adaptive_wakeup_service", lambda: service)
    result = SubAgentResult(
        task_id="task-1", agent_type="researcher", success=False, result="", error="oops", duration_seconds=0.1
    )

    await ServerWakeupHandler().on_async_wakeup(result, "planner", chat_session_id("abc"))
    while wakeup_handler._tasks:
        await asyncio.gather(*list(wakeup_handler._tasks))

    service.handle_settlement.assert_awaited_once()
