"""Shared parallel subagent execution for batch delegate and swarm fission.

[INPUT]
- parent_agent: BaseAgent that owns the delegations and their workspace
- delegate_tool: delegate_task tool whose coroutine runs one task
- tasks: list[TaskRequest] to run concurrently

[OUTPUT]
- run_parallel_task_requests: dict with the batch summary, per-task results and budget admission

[POS]
Parallel execution layer shared by batch delegation and swarm fission. Every child runs inside
``approvals_unanswerable()`` because an approval request raised by one of several concurrent tasks
cannot be shown to the user; the child is declined with a readable reason instead.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool

from myrm_agent_harness.agent.parallel.config import DEFAULT_MAX_BATCH_PARALLEL
from myrm_agent_harness.agent.parallel.summary import (
    batch_summary,
    inject_capacity_signal,
)
from myrm_agent_harness.agent.sub_agents.approval_journal import approvals_unanswerable
from myrm_agent_harness.utils.logger_utils import get_agent_logger

if TYPE_CHECKING:
    from myrm_agent_harness.agent.base_agent import BaseAgent
    from myrm_agent_harness.agent.meta_tools.spawn_subagent._delegate_batch import (
        TaskRequest,
    )
    from myrm_agent_harness.agent.meta_tools.spawn_subagent._delegate_budget import (
        _BatchBudgetAdmission,
    )

logger = get_agent_logger(__name__)


async def run_parallel_task_requests(
    *,
    parent_agent: BaseAgent,
    delegate_tool: BaseTool,
    tasks: list[TaskRequest],
    wait: bool = True,
    race: bool = False,
    max_concurrent: int | None = None,
    budget_admission: _BatchBudgetAdmission | None = None,
    on_progress: Callable[[int, str, dict[str, object] | None], Awaitable[None]] | None = None,
    strict_completeness: bool = False,
    min_completeness_ratio: float = 0.0,
) -> dict[str, object]:
    """Run TaskRequest items concurrently via an existing delegate_task tool."""
    if not tasks:
        return {"success": False, "error": "No tasks provided."}

    if max_concurrent is not None:
        effective_concurrent = max(1, min(max_concurrent, len(tasks), DEFAULT_MAX_BATCH_PARALLEL))
    else:
        effective_concurrent = 3 if race else 1
    semaphore = asyncio.Semaphore(effective_concurrent)

    async def _run_task(task: TaskRequest, index: int) -> dict[str, object]:
        if on_progress:
            await on_progress(index, "running", None)
        async with semaphore:
            coroutine = getattr(delegate_tool, "coroutine", None)
            if coroutine is None:
                err_res = {
                    "success": False,
                    "error": "delegate_task tool has no async coroutine",
                    "task_index": index,
                    "agent_type": task.agent_type,
                }
                if on_progress:
                    await on_progress(index, "failed", err_res)
                return err_res
            with approvals_unanswerable():
                res = await coroutine(
                    agent_type=task.agent_type,
                    objective=task.objective,
                    context_files=task.context_files,
                    context=task.context,
                    wait=wait or race,
                    readonly=task.readonly,
                    complexity_tier=task.complexity_tier,
                    role=task.role,
                    verifier_prompt=task.verifier_prompt,
                    verifier_agent_type=task.verifier_agent_type,
                    max_verification_rounds=task.max_verification_rounds,
                )
            if isinstance(res, dict):
                res.setdefault("agent_type", task.agent_type)
                res["task_index"] = index
                if on_progress:
                    status = "completed" if res.get("success") else "failed"
                    await on_progress(index, status, res)
                return res

            err_res = {
                "success": False,
                "error": str(res),
                "task_index": index,
                "agent_type": task.agent_type,
            }
            if on_progress:
                await on_progress(index, "failed", err_res)
            return err_res

    if race:
        pending_tasks: set[asyncio.Task[dict[str, object]]] = {
            asyncio.create_task(_run_task(task, index)) for index, task in enumerate(tasks)
        }
        winner_result: dict[str, object] | None = None
        failed_results: list[object] = []

        while pending_tasks:
            done, pending_tasks = await asyncio.wait(pending_tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                try:
                    res = task.result()
                    if isinstance(res, dict) and res.get("success"):
                        winner_result = res
                        break
                    failed_results.append(res)
                except Exception as exc:
                    logger.warning("A speculative execution task failed: %s", exc)
                    failed_results.append({"success": False, "error": str(exc)})

            if winner_result:
                for task in pending_tasks:
                    task.cancel()
                break

        if winner_result:
            return inject_capacity_signal(
                {
                    "success": True,
                    "status": "completed",
                    "race_winner": True,
                    "result": winner_result,
                    "budget_admission": (budget_admission.to_dict() if budget_admission else None),
                },
                parent_agent,
            )

        normalized_failures = [
            res if isinstance(res, dict) else {"success": False, "error": str(res)} for res in failed_results
        ]
        return inject_capacity_signal(
            {
                "success": False,
                "status": "failed",
                "error": "All speculative execution tasks failed.",
                "failed_results": failed_results,
                **batch_summary(normalized_failures),
                "budget_admission": (budget_admission.to_dict() if budget_admission else None),
            },
            parent_agent,
        )

    coros = [_run_task(task, index) for index, task in enumerate(tasks)]
    gathered = await asyncio.gather(*coros, return_exceptions=True)

    final_results: list[dict[str, object]] = []
    for index, gathered_result in enumerate(gathered):
        if isinstance(gathered_result, Exception):
            final_results.append(
                {
                    "success": False,
                    "error": str(gathered_result),
                    "task_index": index,
                    "agent_type": tasks[index].agent_type,
                }
            )
        elif isinstance(gathered_result, dict):
            final_results.append(gathered_result)
        else:
            final_results.append(
                {
                    "success": False,
                    "error": str(gathered_result),
                    "task_index": index,
                    "agent_type": tasks[index].agent_type,
                }
            )

    summary_data = batch_summary(final_results)
    gate_passed = True
    gate_error: str | None = None

    if strict_completeness and not summary_data.get("all_success"):
        gate_passed = False
        gate_error = (
            f"Strict completeness gate failed: {summary_data.get('failed_count')} of "
            f"{summary_data.get('total_count')} tasks failed."
        )
    elif min_completeness_ratio > 0.0:
        raw_ratio = summary_data.get("completeness_ratio")
        ratio = float(raw_ratio) if isinstance(raw_ratio, int | float) else 0.0
        if ratio < min_completeness_ratio:
            gate_passed = False
            gate_error = (
                f"Fleet completeness ratio {ratio:.1%} is below required threshold {min_completeness_ratio:.1%}."
            )

    if not gate_passed:
        summary_data["gate_passed"] = False
        summary_data["success"] = False
        summary_data["completeness_gate_error"] = gate_error

    payload: dict[str, object] = {
        **summary_data,
        "results": final_results,
        "budget_admission": (budget_admission.to_dict() if budget_admission else None),
    }
    return inject_capacity_signal(payload, parent_agent)
