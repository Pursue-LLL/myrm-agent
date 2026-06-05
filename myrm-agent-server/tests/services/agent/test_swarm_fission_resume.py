"""Extended swarm fission resume stream tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.swarm_fission_resume import stream_with_swarm_fission_resume


@pytest.mark.asyncio
async def test_stream_with_swarm_fission_resume_loop() -> None:
    agent = MagicMock()
    fission_payload = {
        "action_type": "swarm_fission",
        "tasks": [
            {"agent_type": "research", "objective": "Task A"},
        ],
    }
    resume_result = {
        "success": True,
        "status": "completed",
        "completed_count": 1,
        "failed_count": 0,
        "partial_success": False,
        "results": [{"agent_type": "research", "success": True, "result": "ok"}],
    }

    call_index = 0

    async def open_stream(_query_input: object):
        nonlocal call_index
        call_index += 1
        if call_index == 1:
            yield {"type": "swarm_fission", "data": fission_payload}
            return
        yield {"type": "message", "data": "done"}

    execute_mock = AsyncMock(return_value=resume_result)

    events: list[dict[str, object]] = []
    with patch(
        "app.services.agent.swarm_fission_resume.execute_swarm_fission_for_agent",
        execute_mock,
    ):
        async for event in stream_with_swarm_fission_resume(
            agent,
            "initial query",
            open_stream,
            max_concurrent=3,
        ):
            events.append(event)

    assert execute_mock.await_count == 1
    running = next(e for e in events if e.get("type") == "tasks_steps" and e.get("status") == "running")
    assert running.get("data") == [{"text": "Task A", "agent_type": "research", "task_index": 0}]
    completed = next(e for e in events if e.get("type") == "tasks_steps" and e.get("status") == "completed")
    assert completed.get("failed_count") == 0
    assert completed.get("completed_count") == 1
    assert any(event.get("type") == "message" for event in events)
    assert call_index == 2


@pytest.mark.asyncio
async def test_stream_with_swarm_fission_partial_failure_emits_fields() -> None:
    agent = MagicMock()
    fission_payload = {
        "action_type": "swarm_fission",
        "tasks": [
            {"agent_type": "research", "objective": "Task A"},
            {"agent_type": "research", "objective": "Task B"},
        ],
    }
    resume_result = {
        "success": False,
        "status": "partial_success",
        "completed_count": 1,
        "failed_count": 1,
        "partial_success": True,
        "results": [
            {"success": True, "result": "ok"},
            {"success": False, "error": "timeout"},
        ],
    }

    call_index = 0

    async def open_stream(_query_input: object):
        nonlocal call_index
        call_index += 1
        if call_index == 1:
            yield {"type": "swarm_fission", "data": fission_payload}
            return
        yield {"type": "message", "data": "done"}

    execute_mock = AsyncMock(return_value=resume_result)

    events: list[dict[str, object]] = []
    with patch(
        "app.services.agent.swarm_fission_resume.execute_swarm_fission_for_agent",
        execute_mock,
    ):
        async for event in stream_with_swarm_fission_resume(
            agent,
            "initial query",
            open_stream,
        ):
            events.append(event)

    completed = next(e for e in events if e.get("type") == "tasks_steps" and e.get("status") == "partial_success")
    assert completed.get("failed_count") == 1
    assert completed.get("partial_success") is True


@pytest.mark.asyncio
async def test_stream_with_swarm_fission_delegate_missing_emits_error() -> None:
    agent = MagicMock()
    fission_payload = {
        "action_type": "swarm_fission",
        "tasks": [{"agent_type": "research", "objective": "Task A"}],
    }
    resume_result = {
        "success": False,
        "status": "failed",
        "error": "Parent agent has no delegate_task tool installed.",
        "completed_count": 0,
        "failed_count": 1,
        "results": [],
    }

    call_index = 0

    async def open_stream(_query_input: object):
        nonlocal call_index
        call_index += 1
        if call_index == 1:
            yield {"type": "swarm_fission", "data": fission_payload}
            return
        yield {"type": "message", "data": "done"}

    execute_mock = AsyncMock(return_value=resume_result)

    events: list[dict[str, object]] = []
    with patch(
        "app.services.agent.swarm_fission_resume.execute_swarm_fission_for_agent",
        execute_mock,
    ):
        async for event in stream_with_swarm_fission_resume(
            agent,
            "initial query",
            open_stream,
        ):
            events.append(event)

    assert any(event.get("type") == "error" and event.get("error_type") == "swarm_fission" for event in events)
