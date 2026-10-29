"""A child whose result a caller is blocked on does not also wake the parent.

The parent's wakeup delivers a result nobody is waiting for. ``spawn_child(wait=True)`` and ``wait_children`` hand the
result to their caller, so waking the parent as well would start a second turn that repeats it. A child that outlives
the wait (timeout) is back to being nobody's, and wakes the parent when it settles. The spawn, the wait and the cleanup
are the real ``SubagentManager``; only the child run is scripted.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from unittest.mock import MagicMock, patch

import pytest

from myrm_agent_harness.agent.sub_agents._awaited_children import AwaitedChildren
from myrm_agent_harness.agent.sub_agents.manager import SubagentManager
from myrm_agent_harness.agent.sub_agents.types import SubagentConfig, SubAgentResult, SubAgentStatus

ChildRun = Callable[..., Awaitable[SubAgentResult]]


class _Parent:
    """Minimal parent agent: the surface ``_cleanup_child`` and ``spawn_child`` touch."""

    session_id = "awaited-wakeup-session"

    def __init__(self) -> None:
        self.woken: list[str] = []

    async def trigger_async_wakeup(self, result: SubAgentResult) -> None:
        self.woken.append(result.task_id)


@pytest.fixture
def parent() -> _Parent:
    return _Parent()


@pytest.fixture
def manager(parent: _Parent) -> SubagentManager:
    with patch("myrm_agent_harness.agent.hooks.graceful_shutdown.get_shutdown_manager", return_value=MagicMock()):
        return SubagentManager(parent_agent=parent)  # type: ignore[arg-type]


def _finishes_after(seconds: float) -> ChildRun:
    async def run_child(*, task_id: str, agent_type: str, **_: object) -> SubAgentResult:
        await asyncio.sleep(seconds)
        return SubAgentResult(
            success=True,
            task_id=task_id,
            agent_type=agent_type,
            result="done",
            completed_at=time.time(),
            status=SubAgentStatus.COMPLETED,
        )

    return run_child


async def _spawn(manager: SubagentManager, task_id: str, *, wait: bool, timeout: float | None = None) -> object:
    config = SubagentConfig(system_prompt="researcher")
    if timeout is not None:
        # The config clamps its timeout to a minimum that would make this test slow.
        object.__setattr__(config, "timeout_seconds", timeout)
    return await manager.spawn_child(
        task_id=task_id,
        agent_type="researcher",
        task_description="look into it",
        config=config,
        context={},
        tool_registry_getter=list,
        wait=wait,
    )


async def _settle(manager: SubagentManager) -> None:
    """Let every child finish and every wakeup the cleanup started run to the end."""
    await asyncio.gather(*manager.children.values(), return_exceptions=True)
    await asyncio.sleep(0)
    await asyncio.gather(*manager._background_tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_a_foreground_child_hands_its_result_to_the_caller_and_does_not_wake_the_parent(
    manager: SubagentManager, parent: _Parent
) -> None:
    with patch.object(manager, "_run_subagent", _finishes_after(0)):
        outcome = await _spawn(manager, "fg-1", wait=True)
        await _settle(manager)

    assert isinstance(outcome, SubAgentResult) and outcome.success
    assert parent.woken == []


@pytest.mark.asyncio
async def test_a_background_child_wakes_the_parent_once(manager: SubagentManager, parent: _Parent) -> None:
    with patch.object(manager, "_run_subagent", _finishes_after(0)):
        await _spawn(manager, "bg-1", wait=False)
        await _settle(manager)

    assert parent.woken == ["bg-1"]


@pytest.mark.asyncio
async def test_a_foreground_child_that_outlives_the_wait_wakes_the_parent_when_it_settles(
    manager: SubagentManager, parent: _Parent
) -> None:
    with patch.object(manager, "_run_subagent", _finishes_after(0.2)):
        outcome = await _spawn(manager, "slow-1", wait=True, timeout=0.05)
        assert isinstance(outcome, SubAgentResult) and outcome.still_running
        assert parent.woken == []
        await _settle(manager)

    assert parent.woken == ["slow-1"]


@pytest.mark.asyncio
async def test_children_collected_by_wait_children_do_not_wake_the_parent(
    manager: SubagentManager, parent: _Parent
) -> None:
    with patch.object(manager, "_run_subagent", _finishes_after(0.02)):
        for index in range(3):
            await _spawn(manager, f"alt-{index}", wait=False)
        batch = await manager.wait_children(["alt-0", "alt-1", "alt-2"], min_success_rate=0.0)
        await _settle(manager)

    assert batch["success_rate"] == 1.0
    assert parent.woken == []


@pytest.mark.asyncio
async def test_a_child_still_running_when_wait_children_times_out_wakes_the_parent_when_it_settles(
    manager: SubagentManager, parent: _Parent
) -> None:
    with patch.object(manager, "_run_subagent", _finishes_after(0.2)):
        await _spawn(manager, "bg-slow", wait=False)
        await manager.wait_children(["bg-slow"], min_success_rate=0.0, timeout=0.05)
        assert parent.woken == []
        await _settle(manager)

    assert parent.woken == ["bg-slow"]


@pytest.mark.asyncio
async def test_a_wait_that_is_cancelled_releases_its_children(manager: SubagentManager, parent: _Parent) -> None:
    with patch.object(manager, "_run_subagent", _finishes_after(0.2)):
        await _spawn(manager, "bg-cancelled-wait", wait=False)
        waiter = asyncio.create_task(manager.wait_children(["bg-cancelled-wait"], min_success_rate=0.0))
        await asyncio.sleep(0.02)
        assert "bg-cancelled-wait" in manager.awaited_children
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
        assert "bg-cancelled-wait" not in manager.awaited_children
        await _settle(manager)

    assert parent.woken == ["bg-cancelled-wait"]


def test_a_child_two_callers_wait_on_stays_awaited_until_both_are_done() -> None:
    awaited = AwaitedChildren()

    with awaited.held(["child"]):
        with awaited.held(["child", "other"]):
            assert "child" in awaited and "other" in awaited
        assert "child" in awaited and "other" not in awaited
    assert "child" not in awaited


def test_a_hold_is_released_when_the_block_raises() -> None:
    awaited = AwaitedChildren()

    with pytest.raises(RuntimeError), awaited.held(["child"]):
        raise RuntimeError("the wait failed")

    assert "child" not in awaited
