"""Runtime E2E tests for swarm fission web-style resume loops."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.swarm_fission_resume import stream_with_swarm_fission_resume


@pytest.mark.asyncio
async def test_web_fission_interrupt_resume_message_e2e() -> None:
    """Simulate Web path: fission yield -> parallel execute -> resume -> final message."""
    agent = MagicMock()
    fission_payload = {
        "action_type": "swarm_fission",
        "tasks": [
            {"agent_type": "research", "objective": "Research A"},
            {"agent_type": "research", "objective": "Research B"},
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
        yield {"type": "message", "data": "Synthesized report"}

    execute_mock = AsyncMock(return_value=resume_result)
    events: list[dict[str, object]] = []
    with patch(
        "app.services.agent.swarm_fission_resume.execute_swarm_fission_for_agent",
        execute_mock,
    ):
        async for event in stream_with_swarm_fission_resume(
            agent,
            "compare competitors",
            open_stream,
            max_concurrent=3,
        ):
            events.append(event)

    assert call_index == 2
    assert execute_mock.await_count == 1

    running = [e for e in events if e.get("type") == "tasks_steps" and e.get("status") == "running"]
    assert len(running) == 1
    assert running[0].get("count") == 2

    partial = [e for e in events if e.get("type") == "tasks_steps" and e.get("status") == "partial_success"]
    assert len(partial) == 1
    assert partial[0].get("failed_count") == 1
    assert partial[0].get("partial_success") is True

    assert any(e.get("type") == "message" and e.get("data") == "Synthesized report" for e in events)


def test_parallel_task_results_partial_success_field() -> None:
    from myrm_agent_harness.agent.parallel.schemas import ParallelTaskResults

    parsed = ParallelTaskResults.from_batch_dict(
        {
            "success": False,
            "status": "partial_success",
            "completed_count": 1,
            "failed_count": 1,
            "partial_success": True,
            "results": [],
        }
    )
    assert parsed.partial_success is True
    assert parsed.failed_count == 1
    assert "partial_success" in parsed.to_resume_dict()
