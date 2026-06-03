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
    on_progress: Callable[[int, str, dict[str, object] | None], Awaitable[None]] | None = None,
) -> dict[str, object]:
    from myrm_agent_harness.agent.parallel.fission import execute_swarm_fission

    return await execute_swarm_fission(
        agent,
        fission_payload,
        max_concurrent=max_concurrent,
        on_progress=on_progress,
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
    import asyncio
    import uuid
    import logging
    from langgraph.types import Command
    
    from app.database.session import async_session_maker
    from app.database.repositories.fission_repo import FissionRepository
    from app.channels.types.messages import FissionTopologyNode, FissionTopologyUpdate

    logger = logging.getLogger(__name__)
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
            
        fission_id = str(uuid.uuid4())
        fission_queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

        async def _fission_on_progress(index: int, status: str, res: dict[str, object] | None) -> None:
            await fission_queue.put({"index": index, "status": status, "res": res})

        task_items = _task_items_from_payload(fission_payload)
        nodes_state: dict[int, dict[str, object]] = {}
        for item in task_items:
            nodes_state[item["task_index"]] = {
                "node_id": f"node_{item['task_index']}",
                "agent_type": item["agent_type"],
                "objective": item["text"],
                "status": "pending",
                "error": None,
                "cost_usd": 0.0
            }
            
        async def _save_to_db() -> None:
            try:
                chat_id_from_agent = "default"
                if hasattr(agent, "_current_chat_id") and agent._current_chat_id:
                    chat_id_from_agent = agent._current_chat_id
                agent_id = agent.id if hasattr(agent, "id") else "default_agent"
                
                async with async_session_maker() as db:
                    await FissionRepository.create_or_update_record(
                        db,
                        fission_id=fission_id,
                        chat_id=chat_id_from_agent,
                        agent_id=agent_id,
                        nodes=list(nodes_state.values()),
                        total_cost_usd=0.0,
                    )
            except Exception as e:
                logger.error("Failed to persist fission state to DB: %s", e)
                
        await _save_to_db()

        fission_task = asyncio.create_task(
            execute_swarm_fission_for_agent(
                agent,
                fission_payload,
                max_concurrent=effective_concurrent,
                on_progress=_fission_on_progress,
            )
        )

        while not fission_task.done() or not fission_queue.empty():
            try:
                # Wait for queue items or task completion
                get_task = asyncio.create_task(fission_queue.get())
                done, pending = await asyncio.wait(
                    [get_task, fission_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # If we didn't consume get_task, cancel it
                if get_task in pending:
                    get_task.cancel()
                
                # Process all items currently in queue
                needs_db_sync = False
                while not fission_queue.empty():
                    progress = fission_queue.get_nowait()
                    idx = int(progress.get("index", -1))
                    if idx in nodes_state:
                        nodes_state[idx]["status"] = progress.get("status", "running")
                        res_info = progress.get("res")
                        if isinstance(res_info, dict):
                            if "error" in res_info:
                                nodes_state[idx]["error"] = str(res_info["error"])
                    needs_db_sync = True
                
                if needs_db_sync:
                    await _save_to_db()
                    
                    # Yield topology update out to the channel bridge
                    nodes_tuple = tuple(FissionTopologyNode(**n) for n in nodes_state.values())
                    topo_update = FissionTopologyUpdate(
                        fission_id=fission_id,
                        nodes=nodes_tuple,
                        total_cost_usd=0.0
                    )
                    yield {"type": "fission_topology", "data": topo_update}
                    
            except Exception as e:
                logger.error("Error processing fission queue: %s", e)
                break

        fission_result = fission_task.result()
        
        # Ensure final state is saved
        await _save_to_db()

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
