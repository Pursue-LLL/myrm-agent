"""`subagent_control_tool action=list` hands the agent every settled result, so it reports them as read."""

from __future__ import annotations

from collections.abc import Collection, Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.agent.meta_tools.spawn_subagent.agent_manage_tool import create_subagent_control_tool
from myrm_agent_harness.agent.sub_agents.types import SubAgentResult, SubAgentStatus
from myrm_agent_harness.utils.runtime.wakeup_registry import set_global_wakeup_handler


class _Handler:
    def __init__(self) -> None:
        self.reads: list[tuple[tuple[str, ...], str | None]] = []

    async def on_async_wakeup(self, result: SubAgentResult, agent_id: str, session_id: str | None) -> None:
        raise AssertionError("listing results never wakes anyone")

    def on_results_read(self, task_ids: Collection[str], session_id: str | None) -> None:
        self.reads.append((tuple(task_ids), session_id))


@pytest.fixture
def handler() -> Iterator[_Handler]:
    registered = _Handler()
    set_global_wakeup_handler(registered)
    yield registered
    set_global_wakeup_handler(None)


def _done(task_id: str) -> dict[str, object]:
    return {"task_id": task_id, "status": SubAgentStatus.COMPLETED.value}


def _parent(children: list[dict[str, object]], context: dict[str, object] | None = None) -> MagicMock:
    parent = MagicMock()
    parent.list_children.return_value = children
    parent._last_context = {"session_id": "chat-1"} if context is None else context
    return parent


@pytest.mark.asyncio
async def test_listing_reports_the_children_with_a_final_result_and_no_others(handler: _Handler) -> None:
    children: list[dict[str, object]] = [
        {"task_id": "done-1", "status": SubAgentStatus.COMPLETED.value, "result": "found it"},
        {"task_id": "going", "status": SubAgentStatus.RUNNING.value},
        {"task_id": "broke", "status": SubAgentStatus.FAILED.value, "result": ""},
        {"task_id": "slow", "status": SubAgentStatus.TIMED_OUT.value, "result": ""},
        {"task_id": "spent", "status": SubAgentStatus.CANCELLED_BY_BUDGET.value, "result": ""},
        {"task_id": "asking", "status": SubAgentStatus.PENDING_APPROVAL.value},
    ]
    tool = create_subagent_control_tool(_parent(children))

    listing = await tool.ainvoke({"action": "list"})

    assert (listing["total"], listing["running"], listing["completed"]) == (6, 1, 5)
    assert handler.reads == [(("done-1", "broke", "slow", "spent"), "chat-1")]


@pytest.mark.asyncio
async def test_a_listing_with_nothing_settled_reports_nothing(handler: _Handler) -> None:
    running: dict[str, object] = {"task_id": "going", "status": SubAgentStatus.RUNNING.value}
    tool = create_subagent_control_tool(_parent([running]))

    await tool.ainvoke({"action": "list"})

    assert handler.reads == []


@pytest.mark.asyncio
async def test_a_parent_without_a_session_reports_with_none(handler: _Handler) -> None:
    tool = create_subagent_control_tool(_parent([_done("done-1")], context={}))

    await tool.ainvoke({"action": "list"})

    assert handler.reads == [(("done-1",), None)]


@pytest.mark.asyncio
async def test_a_handler_that_fails_does_not_fail_the_listing() -> None:
    failing = _Handler()
    failing.on_results_read = MagicMock(side_effect=RuntimeError("handler down"))  # type: ignore[method-assign]
    set_global_wakeup_handler(failing)
    try:
        tool = create_subagent_control_tool(_parent([_done("done-1")]))

        listing = await tool.ainvoke({"action": "list"})
    finally:
        set_global_wakeup_handler(None)

    assert listing["completed"] == 1


@pytest.mark.asyncio
async def test_the_other_actions_report_nothing(handler: _Handler) -> None:
    parent = _parent([_done("done-1")])
    parent.cancel_child.return_value = False
    parent.wait_children = AsyncMock(return_value={"results": [], "failures": []})
    tool = create_subagent_control_tool(parent)

    await tool.ainvoke({"action": "cancel", "task_id": "done-1"})
    await tool.ainvoke({"action": "wait", "task_id": "done-1", "timeout_seconds": 1})

    assert handler.reads == []
