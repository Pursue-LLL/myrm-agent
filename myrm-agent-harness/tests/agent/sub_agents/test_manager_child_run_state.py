"""Children the real manager runs keep what their run leaves in the guards apart from their parent's.

``SubagentManager`` runs each child as an asyncio task through the executor's retry path, which opens the
child's run in ``child_run_scope``. Whatever the child's run does to the guards (finish, be cancelled, pause
for approval and be resumed, run next to a sibling), the parent's guards come back as they were, and the
child's own loop guard lives exactly as long as the delegation can still be resumed. The child agents here
open and use their guards the way a run does; the manager, the executor and the scope are real.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from types import SimpleNamespace
from typing import Protocol
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.types import Command

from myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware import (
    _session_loop_guards,
    get_loop_guard,
)
from myrm_agent_harness.agent.streaming.types import AgentEventType
from myrm_agent_harness.agent.sub_agents.manager import SubagentManager
from myrm_agent_harness.agent.sub_agents.types import (
    CancellationStrategy,
    SubagentConfig,
    SubAgentResult,
    SubAgentStatus,
)
from tests.agent.sub_agents.guard_state_probe import (
    CHILD_TURN,
    GuardState,
    guard_state,
    start_run,
    turn_registries,
    use_every_guard,
)

pytestmark = pytest.mark.usefixtures("parent_run")

_Pause = Callable[[], Awaitable[None]]
_ANSWER = {"type": AgentEventType.MESSAGE.value, "data": "done"}
_PENDING_APPROVAL = SimpleNamespace(tasks=[SimpleNamespace(interrupts=[SimpleNamespace(value={"kind": "approval"})])])


def _manager() -> SubagentManager:
    with patch("myrm_agent_harness.agent.hooks.graceful_shutdown.get_shutdown_manager", return_value=MagicMock()):
        parent = MagicMock()
        parent._last_context = {}
        return SubagentManager(parent_agent=parent)


def _child(
    *, turn: str = CHILD_TURN, is_resume: bool = False, pause: _Pause | None = None, ask_approval: bool = False
) -> MagicMock:
    """A child agent whose run opens its guards like a run does, uses them, optionally waits, then answers."""

    async def run(**_: object) -> AsyncIterator[dict[str, object]]:
        start_run(turn=turn, is_resume=is_resume)
        use_every_guard(error="sandbox_denied")
        if pause is not None:
            await pause()
        yield _ANSWER

    child = MagicMock()
    child.run = run
    child.last_run_stats = MagicMock(token_usage=None)
    child._agent = MagicMock(aget_state=AsyncMock(return_value=_PENDING_APPROVAL if ask_approval else None))
    return child


class _Spawn(Protocol):
    def __call__(
        self,
        manager: SubagentManager,
        task_id: str,
        child: MagicMock,
        *,
        wait: bool = True,
        resume: Command[object] | None = None,
    ) -> Awaitable[SubAgentResult | dict[str, object]]: ...


@pytest.fixture
def spawn() -> Iterator[_Spawn]:
    """Spawn a child agent through the manager; the executor builds the child the test registered for the task.

    The seams stay patched for the test's whole length: a detached child builds its agent after ``spawn_child`` returned.
    """
    agents: dict[str, MagicMock] = {}

    async def build_child_agent(
        _config: object, _tools: object, task_description: str, *_: object, **__: object
    ) -> MagicMock:
        return agents[task_description]

    async def spawn_child(
        manager: SubagentManager,
        task_id: str,
        child: MagicMock,
        *,
        wait: bool = True,
        resume: Command[object] | None = None,
    ) -> SubAgentResult | dict[str, object]:
        agents[task_id] = child
        return await manager.spawn_child(
            task_id=task_id,
            agent_type="worker",
            task_description=task_id,
            config=SubagentConfig(system_prompt="child", cancellation_strategy=CancellationStrategy.IMMEDIATE),
            context={},
            tool_registry_getter=list,
            wait=wait,
            resume_command=resume,
            internal=True,
        )

    with (
        patch("myrm_agent_harness.agent.sub_agents.executor_attempt_mixin.build_child_agent", build_child_agent),
        patch("myrm_agent_harness.agent.sub_agents.executor_attempt_mixin._parse_handover_state", return_value=None),
        patch(
            "myrm_agent_harness.agent.sub_agents.executor_attempt_mixin._auto_vault_or_truncate",
            side_effect=lambda text, *args, **kwargs: text,
        ),
    ):
        yield spawn_child


async def _settle(manager: SubagentManager) -> None:
    """Let every child task finish and its done-callback release what the manager keeps for it."""
    await asyncio.gather(*manager.children.values(), return_exceptions=True)
    await asyncio.sleep(0)


async def test_a_finished_child_leaves_its_parents_guards_alone_and_nothing_of_its_own(spawn: _Spawn) -> None:
    parent, registries = guard_state(), turn_registries()
    manager = _manager()

    result = await spawn(manager, "task_a", _child())

    assert isinstance(result, SubAgentResult) and result.status is SubAgentStatus.COMPLETED
    assert guard_state() == parent
    assert turn_registries() == registries
    assert "task_a" not in _session_loop_guards


async def test_a_cancelled_child_leaves_its_parents_guards_alone_and_nothing_of_its_own(spawn: _Spawn) -> None:
    parent, registries = guard_state(), turn_registries()
    manager = _manager()
    running, forever = asyncio.Event(), asyncio.Event()

    async def block() -> None:
        running.set()
        await forever.wait()

    await spawn(manager, "task_a", _child(pause=block), wait=False)
    await running.wait()
    assert manager.cancel_child("task_a")
    await _settle(manager)

    assert guard_state() == parent
    assert turn_registries() == registries
    assert "task_a" not in _session_loop_guards


async def test_a_child_waiting_for_approval_keeps_its_loop_guard_until_the_resume_ends(spawn: _Spawn) -> None:
    parent = guard_state()
    manager = _manager()

    paused = await spawn(manager, "task_a", _child(ask_approval=True))

    assert isinstance(paused, SubAgentResult) and paused.status is SubAgentStatus.PENDING_APPROVAL
    kept = _session_loop_guards["task_a"]
    assert len(kept._window) == 1
    assert guard_state() == parent

    seen: list[tuple[bool, int]] = []

    async def note_loop_guard() -> None:
        seen.append((get_loop_guard() is kept, len(get_loop_guard()._window)))

    resumed = await spawn(
        manager,
        "task_a",
        _child(turn="turn_resumed", is_resume=True, pause=note_loop_guard),
        resume=Command(resume="ok"),
    )

    assert isinstance(resumed, SubAgentResult) and resumed.status is SubAgentStatus.COMPLETED
    assert seen == [(True, 2)]
    assert guard_state() == parent
    assert "task_a" not in _session_loop_guards


async def test_children_running_at_once_each_keep_their_own_turn_state_and_their_parents(spawn: _Spawn) -> None:
    parent, registries = guard_state(), turn_registries()
    manager = _manager()
    both_started, release = asyncio.Event(), asyncio.Event()
    started: list[str] = []
    own_state: dict[str, GuardState] = {}

    def child(name: str) -> MagicMock:
        async def hold() -> None:
            started.append(name)
            if len(started) == 2:
                both_started.set()
            await release.wait()
            own_state[name] = guard_state()

        return _child(turn=f"turn_{name}", pause=hold)

    await spawn(manager, "task_a", child("a"), wait=False)
    await spawn(manager, "task_b", child("b"), wait=False)
    await both_started.wait()
    release.set()
    await _settle(manager)

    assert set(own_state) == {"a", "b"}
    assert all(state.turn_refusals == 1 and state.turn_evidence == 1 for state in own_state.values())
    assert guard_state() == parent
    assert turn_registries() == registries
    assert not {"task_a", "task_b"} & set(_session_loop_guards)
