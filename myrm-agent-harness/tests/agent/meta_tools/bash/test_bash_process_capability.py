"""Capability gate of bash_process_tool: acting on a job needs EXECUTE, observing it does not.

A delegated child shares the delegating agent's session, so the session scoping alone lets a
read-only child signal or feed the parent's background jobs.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from dataclasses import replace
from typing import cast, get_args
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool

from myrm_agent_harness.agent.meta_tools.bash._background.registry import get_background_registry
from myrm_agent_harness.agent.meta_tools.bash.bash_process_tools import _BashProcessInput, create_bash_process_tool
from myrm_agent_harness.core.security.ocap import (
    CapabilityAction,
    CapabilityHandle,
    ResourceScope,
    capability_scope,
    sign_capability_handle,
)
from myrm_agent_harness.core.security.tool_registry import resolve_permission_type
from myrm_agent_harness.toolkits.code_execution.executors.models import AsyncProcessProtocol

_SESSION = "sess-capability-gate"
_PID = 7301
_CONFIG: RunnableConfig = {"configurable": {"context": {"session_id": _SESSION}}}
_ACTING_CALLS = (
    {"action": "kill", "pid": _PID},
    {"action": "write_stdin", "pid": _PID, "data": "x"},
    {"action": "submit_stdin", "pid": _PID, "data": "y"},
    {"action": "close_stdin", "pid": _PID},
)


class _FakeStdin:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        self.chunks.append(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


class _Job:
    def __init__(self) -> None:
        self._proc = MagicMock()
        self._proc.pid = _PID
        self.stdin = _FakeStdin()
        self.stdout = None
        self.stderr = None
        self._exit_event = asyncio.Event()

    async def wait(self) -> int:
        await self._exit_event.wait()
        return 0

    def terminate(self) -> None:
        self._exit_event.set()

    def kill(self) -> None:
        self._exit_event.set()


def _handle(*actions: CapabilityAction) -> CapabilityHandle:
    now = time.monotonic()
    unsigned = CapabilityHandle(
        handle_id="cap-process-test",
        issuer_id="parent_agent",
        subject_id="child",
        scope=ResourceScope(),
        actions=frozenset(actions),
        issued_at=now,
        expires_at=now + 3600.0,
    )
    return replace(unsigned, signature=sign_capability_handle(unsigned))


async def _start_job() -> _Job:
    job = _Job()
    await get_background_registry().register(
        cast(AsyncProcessProtocol, job), command="npm run dev", session_id=_SESSION
    )
    return job


@pytest.fixture(autouse=True)
def _clear_registry() -> Iterator[None]:
    registry = get_background_registry()
    registry._entries.clear()
    yield
    registry._entries.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("call", _ACTING_CALLS, ids=lambda call: str(call["action"]))
async def test_read_only_handle_cannot_act_on_a_job(call: dict[str, object]) -> None:
    job = await _start_job()
    registry = get_background_registry()
    with (
        capability_scope(_handle(CapabilityAction.READ)),
        patch.object(registry, "kill", new=AsyncMock(return_value=True)) as kill,
    ):
        result = await create_bash_process_tool().ainvoke(call, config=_CONFIG)

    assert result["metadata"] == {"error": "capability_denied", "action": call["action"]}
    kill.assert_not_awaited()
    assert job.stdin.chunks == []
    assert job.stdin.closed is False


_OBSERVING_ACTIONS = {"list", "output", "wait"}


@pytest.mark.parametrize("action", get_args(_BashProcessInput.model_fields["action"].annotation))
def test_an_action_is_gated_unless_it_only_observes_and_the_approval_layer_agrees(action: str) -> None:
    """A new action must be classified in both places; until then it is gated here and this test fails."""
    gated = action not in _OBSERVING_ACTIONS

    assert (resolve_permission_type("bash_process_tool", {"action": action}) == "shell_exec") is gated


@pytest.mark.asyncio
async def test_an_action_the_gate_does_not_know_is_denied_without_execute() -> None:
    tool = create_bash_process_tool()
    assert isinstance(tool, StructuredTool)
    assert tool.coroutine is not None
    with capability_scope(_handle(CapabilityAction.READ)):
        result = await tool.coroutine(action="reload", config=_CONFIG)

    assert result["metadata"] == {"error": "capability_denied", "action": "reload"}


@pytest.mark.asyncio
async def test_read_only_handle_still_observes_a_job() -> None:
    await _start_job()
    tool = create_bash_process_tool()
    with capability_scope(_handle(CapabilityAction.READ)):
        listed = await tool.ainvoke({"action": "list"}, config=_CONFIG)
        output = await tool.ainvoke({"action": "output", "pid": _PID}, config=_CONFIG)

    assert cast(dict[str, object], listed["content"])["count"] == 1
    assert output["metadata"]["action"] == "output"
    assert "error" not in output["metadata"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "handle",
    [None, _handle(CapabilityAction.READ, CapabilityAction.EXECUTE)],
    ids=["top_level_without_handle", "handle_with_execute"],
)
async def test_agent_holding_execute_acts_on_a_job(handle: CapabilityHandle | None) -> None:
    job = await _start_job()
    registry = get_background_registry()
    tool = create_bash_process_tool()
    with capability_scope(handle), patch.object(registry, "kill", new=AsyncMock(return_value=True)):
        submitted = await tool.ainvoke({"action": "submit_stdin", "pid": _PID, "data": "y"}, config=_CONFIG)
        killed = await tool.ainvoke({"action": "kill", "pid": _PID}, config=_CONFIG)

    assert submitted["metadata"]["ok"] is True
    assert job.stdin.chunks == [b"y\n"]
    assert killed["metadata"]["killed"] is True
