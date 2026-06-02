"""Swarm Fission yield-resume helpers for agent event streams.

[INPUT]
- myrm_agent_harness.agent.parallel.fission::execute_swarm_fission (POS: Parallel spawn + resume contract)
- myrm_agent_harness.agent.base_agent::BaseAgent (POS: Agent execution base class)

[OUTPUT]
- execute_swarm_fission_for_agent: Run parallel TaskRequest batch for a fission payload
- stream_with_swarm_fission_resume: Wrap agent streams with automatic Yield-Resume loop

[POS]
Server-side Swarm Fission orchestration. Keeps Web, Channel, Kanban, and FastSearch entry
points from duplicating execute_swarm_fission + Command(resume) wiring.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.parallel.config import resolve_max_parallel_fission

if TYPE_CHECKING:
    from myrm_agent_harness.agent.base_agent import BaseAgent


async def execute_swarm_fission_for_agent(
    agent: BaseAgent,
    fission_payload: dict[str, object],
    *,
    max_concurrent: int | None = None,
) -> dict[str, object]:
    from myrm_agent_harness.agent.parallel.fission import execute_swarm_fission

    return await execute_swarm_fission(
        agent,
        fission_payload,
        max_concurrent=max_concurrent,
    )


def _task_count_from_payload(fission_payload: dict[str, object]) -> int:
    raw_tasks = fission_payload.get("tasks")
    if isinstance(raw_tasks, list):
        return len(raw_tasks)
    return 0


def _task_items_from_payload(
    fission_payload: dict[str, object],
) -> list[dict[str, object]]:
    raw_tasks = fission_payload.get("tasks")
    if not isinstance(raw_tasks, list):
        return []
    items: list[dict[str, object]] = []
    for index, entry in enumerate(raw_tasks):
        if not isinstance(entry, dict):
            continue
        objective = entry.get("objective") or entry.get("goal") or ""
        agent_type = entry.get("agent_type") or "general"
        items.append(
            {
                "text": str(objective),
                "agent_type": str(agent_type),
                "task_index": index,
            }
        )
    return items


def _fission_step_status(fission_result: dict[str, object], task_count: int) -> str:
    failed_count = int(fission_result.get("failed_count") or 0)
    completed_count = int(fission_result.get("completed_count") or 0)
    status = str(fission_result.get("status") or "")
    if status == "partial_success" or (failed_count > 0 and completed_count > 0):
        return "partial_success"
    if fission_result.get("success") is True:
        return "completed"
    if failed_count >= task_count and task_count > 0:
        return "error"
    if fission_result.get("error"):
        return "error"
    return "error"


async def stream_with_swarm_fission_resume(
    agent: BaseAgent,
    initial_query: object,
    open_stream: Callable[[object], AsyncGenerator[dict[str, object], None]],
    *,
    max_concurrent: int | None = None,
) -> AsyncGenerator[dict[str, object], None]:
    """Run parallel sub-tasks when swarm_fission is emitted, then resume the parent agent."""
    from langgraph.types import Command

    query_input = initial_query
    effective_concurrent = resolve_max_parallel_fission(max_concurrent)

    while True:
        is_yielded_for_fission = False
        fission_payload: dict[str, object] | None = None

        async for event in open_stream(query_input):
            event_type = event.get("type", "")
            if event_type == "swarm_fission":
                is_yielded_for_fission = True
                raw_payload = event.get("data")
                if isinstance(raw_payload, dict):
                    fission_payload = raw_payload
                task_count = (
                    _task_count_from_payload(fission_payload)
                    if fission_payload is not None
                    else 0
                )
                task_items = (
                    _task_items_from_payload(fission_payload)
                    if fission_payload is not None
                    else []
                )
                yield {
                    "type": "tasks_steps",
                    "step_key": "swarm_fission",
                    "tool_name": "delegate_parallel_tasks_tool",
                    "count": task_count,
                    "status": "running",
                    "data": task_items,
                }
                continue
            yield event

        if not is_yielded_for_fission or fission_payload is None:
            break

        fission_result = await execute_swarm_fission_for_agent(
            agent,
            fission_payload,
            max_concurrent=effective_concurrent,
        )
        task_count = _task_count_from_payload(fission_payload)
        completed_count = int(fission_result.get("completed_count") or 0)
        failed_count = int(fission_result.get("failed_count") or 0)
        partial_success = bool(fission_result.get("partial_success")) or (
            failed_count > 0 and completed_count > 0
        )
        step_status = _fission_step_status(fission_result, task_count)

        if not fission_result.get("success") and fission_result.get("error"):
            yield {
                "type": "error",
                "error": str(fission_result["error"]),
                "error_type": "swarm_fission",
            }

        summary_text = (
            f"{completed_count}/{task_count} parallel tasks completed"
            if failed_count == 0
            else f"{completed_count}/{task_count} completed, {failed_count} failed"
        )
        task_items = _task_items_from_payload(fission_payload)
        yield {
            "type": "tasks_steps",
            "step_key": "swarm_fission",
            "tool_name": "delegate_parallel_tasks_tool",
            "count": task_count,
            "status": step_status,
            "completed_count": completed_count,
            "failed_count": failed_count,
            "partial_success": partial_success,
            "data": [
                *task_items,
                {"text": summary_text},
            ],
        }
        query_input = Command(resume=fission_result)
