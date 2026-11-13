"""ToolConflictGateMiddleware under random arrival orders and cancellations.

Many model messages share one gate. Their calls reach it in random order and some are cancelled at random moments once
they are there, yet calls never overlap wrongly, conflicting calls start in the order the model made them, and nothing
waits for a call that stopped.
"""

from __future__ import annotations

import asyncio
import random
from unittest.mock import MagicMock, call, patch

import pytest
from langchain.agents.middleware import ToolCallRequest
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from myrm_agent_harness.agent.middlewares.concurrency.tool_conflict_gate import ToolConflictGateMiddleware

SAFE = ("file_read_tool", "grep_tool")
UNSAFE = ("file_write_tool", "bash_code_execute_tool")
MESSAGES = 40
# Every call reaches the gate in this test, so no call has to be written off however long the machine stalls.
GRACE = 15.0
RECORD = "myrm_agent_harness.agent.middlewares.concurrency.tool_conflict_gate.record_tool_order"


def _request(name: str, call_id: str, state: dict[str, list[BaseMessage]]) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "id": call_id, "args": {}, "type": "tool_call"},
        tool=None,
        state=state,
        runtime=MagicMock(),
    )


@pytest.mark.parametrize("seed", range(5))
async def test_conflicting_calls_start_in_the_models_order_whatever_the_arrival_order_and_cancellations(
    seed: int,
) -> None:
    rng = random.Random(seed)
    middleware = ToolConflictGateMiddleware(arrival_grace_seconds=GRACE)
    started: list[str] = []
    inside = {"shared": 0, "exclusive": 0}
    violations: list[str] = []
    completed = 0

    async def handler(request: ToolCallRequest) -> ToolMessage:
        nonlocal completed
        call_id = request.tool_call["id"] or ""
        kind = "exclusive" if request.tool_call["name"] in UNSAFE else "shared"
        started.append(call_id)
        inside[kind] += 1
        if inside["exclusive"] > 1 or (inside["exclusive"] and inside["shared"]):
            violations.append(f"{dict(inside)} while {call_id} started")
        try:
            await asyncio.sleep(rng.random() * 0.003)
            completed += 1
        finally:
            inside[kind] -= 1
        return ToolMessage(content="ok", tool_call_id=call_id)

    async def reach_the_gate(request: ToolCallRequest, cancel_after: float | None) -> None:
        await asyncio.sleep(rng.random() * 0.01)
        if cancel_after is not None:
            # The call is cancelled once it is at the gate: while it waits for the calls ahead, in line, or running.
            this_call = asyncio.current_task()
            assert this_call is not None
            asyncio.get_running_loop().call_later(cancel_after, this_call.cancel)
        await middleware.awrap_tool_call(request, handler)

    messages: list[list[tuple[str, str]]] = []
    tasks: list[asyncio.Task[None]] = []
    for number in range(MESSAGES):
        calls = [(f"m{number}-{index}", rng.choice(SAFE + UNSAFE)) for index in range(rng.randint(2, 6))]
        messages.append(calls)
        message = AIMessage(
            content="",
            id=f"message-{number}",
            tool_calls=[{"id": call_id, "name": name, "args": {}} for call_id, name in calls],
        )
        state: dict[str, list[BaseMessage]] = {"messages": [message]}
        for call_id, name in calls:
            cancel_after = rng.random() * 0.01 if rng.random() < 1 / 7 else None
            tasks.append(asyncio.create_task(reach_the_gate(_request(name, call_id, state), cancel_after)))

    with patch(RECORD) as record:
        async with asyncio.timeout(20):
            await asyncio.gather(*tasks, return_exceptions=True)

    position = {call_id: index for index, call_id in enumerate(started)}
    for calls in messages:
        for earlier, (first_id, first_name) in enumerate(calls):
            for second_id, second_name in calls[earlier + 1 :]:
                conflicting = first_name in UNSAFE or second_name in UNSAFE
                if conflicting and first_id in position and second_id in position:
                    assert position[first_id] < position[second_id], f"{second_id} started before {first_id}"
    assert violations == []
    assert inside == {"shared": 0, "exclusive": 0}
    assert completed >= len(tasks) // 2
    assert call("predecessor_absent") not in record.call_args_list
    assert call("turn_unidentified") not in record.call_args_list
    async with asyncio.timeout(1):
        await middleware.awrap_tool_call(_request(UNSAFE[0], "after", {"messages": []}), handler)
