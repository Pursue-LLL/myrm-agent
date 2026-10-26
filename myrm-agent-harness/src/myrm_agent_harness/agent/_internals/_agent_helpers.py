"""Agent runtime helper functions.

Per-run guard resets, child-run guard isolation, query text extraction, idle task scheduling,
usage ledger initialization.

[INPUT]
- agent.middlewares (POS: guard/state reset functions)
- agent.security (POS: security guard reset functions)
- core.context_vars (POS: scoped_value, approval_session_var)
- agent.background_worker (POS: idle task scheduling)
- utils.token_economics (POS: UsageLedger)

[OUTPUT]
- reset_all_guards: Reset all per-request guard state before a new agent run.
- child_run_scope: Run a child agent inline with guards of its own, handing the parent's back untouched afterwards.
- release_child_run_state: Drop what a finished child's session kept (its loop guard).
- extract_query_text: Extract human-readable query string from various input types.
- schedule_post_run_idle_tasks: Enqueue background idle tasks after a successful agent run.
- init_usage_ledger: Attach a UsageLedger to the current request scope.
- pop_checkpoint_incompatible_merged_context: Strip non-serializable callbacks from merged_context before LangGraph checkpoint.

[POS]
Agent runtime helper functions — guard resets, child-run guard isolation, query extraction, idle tasks, usage ledger, checkpoint-safe context stripping.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterator
from contextlib import ExitStack, contextmanager

from myrm_agent_harness.core.context_vars import approval_session_var, scoped_value
from myrm_agent_harness.utils.logger_utils import get_agent_logger
from myrm_agent_harness.utils.token_economics.tracker import set_usage_ledger

logger = get_agent_logger(__name__)

__all__ = [
    "child_run_scope",
    "extract_query_text",
    "init_usage_ledger",
    "pop_checkpoint_incompatible_merged_context",
    "release_child_run_state",
    "reset_all_guards",
    "schedule_post_run_idle_tasks",
]

_background_tasks: set[asyncio.Task[object]] = set()


def _fire_and_forget(coro: Coroutine[object, object, object]) -> None:
    """Schedule a coroutine as a background task without risk of GC collection."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


# LangGraph counts Pregel steps, and one tool round costs two of them: one step executes the model,
# one executes the tool node. Measured on a real graph — bisecting `recursion_limit` against tool
# call counts 0-5 yielded 2, 4, 6, 8, 10, 12 — so the builder's `max_iterations * 2` turn budget is
# already an exact step budget for plain bind-tools turns.
_MIN_RECURSION_NODES = 300


def effective_recursion_limit(config: object) -> int:
    """The ``recursion_limit`` the graph actually runs with.

    ``LoopGuard`` derives its warn/critical/stuck thresholds from this same number, so the graph
    and its guards must read it from one place: a graph that runs wider than the guards assume
    delays every safety threshold by the same factor.

    The configured value is already a step budget (``AgentConfig.from_env`` maps
    ``MYRM_RECURSION_LIMIT`` onto it, and the builder maps ``max_iterations * 2``), so a positive
    value is used as-is: raising it would silently override what the operator set, and 50 steps
    already buys 24 tool rounds. The default rescues only a configuration that never chose one.
    """
    configured = getattr(config, "recursion_limit", None)
    if isinstance(configured, int) and configured > 0:
        return configured
    return _MIN_RECURSION_NODES


def reset_all_guards(
    *,
    is_resume: bool = False,
    graph_recursion_limit: int = 100,
    unattended_mode: bool = False,
) -> None:
    """Reset all per-request guard state before a new agent run.

    Args:
        is_resume: When ``True`` (approval-resume flow), preserve error
            signature counters in LoopGuard so that cross-resume loops
            are still detected.
        graph_recursion_limit: LangGraph recursion limit, forwarded to
            LoopGuard for dynamic budget threshold calculation.
        unattended_mode: When ``True``, enables strict runaway loop circuit breaker
            for background/unattended agent executions.
    """
    from myrm_agent_harness.agent.middlewares._session_context import (
        reset_terminal_errors,
    )
    from myrm_agent_harness.agent.middlewares.approval import reset_denial_counter
    from myrm_agent_harness.agent.middlewares.completion import (
        reset_completion_guard,
    )
    from myrm_agent_harness.agent.middlewares.plan_confirm_middleware import (
        reset_plan_confirm_state,
    )
    from myrm_agent_harness.agent.middlewares.replan_middleware import (
        reset_replan_attempts,
    )
    from myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware import (
        reset_loop_guard,
    )
    from myrm_agent_harness.agent.security.audit import reset_audit_log
    from myrm_agent_harness.agent.security.guards.context_budget import (
        reset_context_budget_guard,
    )
    from myrm_agent_harness.agent.security.guards.frequency_guard import (
        reset_frequency_guard,
    )
    from myrm_agent_harness.agent.security.guards.privacy_tracker import (
        reset_privacy_tracker,
    )
    from myrm_agent_harness.agent.security.guards.taint_tracker import (
        reset_taint_tracker,
    )
    from myrm_agent_harness.agent.security.guards.tool_turn_budget_guard import (
        reset_tool_turn_budget_guard,
    )

    reset_loop_guard(
        is_resume=is_resume,
        graph_recursion_limit=graph_recursion_limit,
        unattended_mode=unattended_mode,
    )
    reset_frequency_guard()
    reset_tool_turn_budget_guard()
    reset_context_budget_guard(is_resume=is_resume)
    reset_replan_attempts()
    reset_plan_confirm_state()
    reset_terminal_errors()
    reset_denial_counter()
    reset_completion_guard()
    reset_taint_tracker()
    reset_audit_log()
    reset_privacy_tracker()

    # Open the per-run store the human's approval notes are handed over in: a gate stashes the
    # note it read from the answer, the tool-call middleware claims it after the tool returned.
    from myrm_agent_harness.core.context_vars import publish_approval_notes

    publish_approval_notes()


@contextmanager
def child_run_scope(task_id: str) -> Iterator[None]:
    """Run a child agent inline, under its own session, without touching what its parent's run has recorded.

    A child runs inside its parent's delegating tool call and shares the context the parent's guards live in.
    Every run starts by resetting those guards in place, so a child that shared them would erase the parent's
    tool-call history, call window, turn and context budgets and terminal errors. Inside this scope the child
    has guards of its own; when it ends the parent's are back as they were, with the session and subagent
    markers the child's run rebinds.

    Keep in step with ``reset_all_guards``: a guard that resets in place needs its isolated counterpart here.
    """
    from myrm_agent_harness.agent.middlewares._session_context import (
        get_is_subagent,
        get_subagent_task_id,
        isolated_terminal_errors,
        set_is_subagent,
        set_subagent_task_id,
    )
    from myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware import child_loop_guard
    from myrm_agent_harness.agent.security.guards.context_budget import isolated_context_budget_guard
    from myrm_agent_harness.agent.security.guards.frequency_guard import isolated_frequency_guard
    from myrm_agent_harness.agent.security.guards.tool_turn_budget_guard import isolated_tool_turn_budget_guard

    was_subagent, parent_task_id = get_is_subagent(), get_subagent_task_id()
    with ExitStack() as scope:
        # The child's loop guard is registered under the session its run will bind, so it is entered second.
        scope.enter_context(scoped_value(approval_session_var, task_id))
        scope.enter_context(child_loop_guard(task_id))
        scope.enter_context(isolated_frequency_guard())
        scope.enter_context(isolated_tool_turn_budget_guard())
        scope.enter_context(isolated_context_budget_guard())
        scope.enter_context(isolated_terminal_errors())
        set_is_subagent(True)
        set_subagent_task_id(task_id)
        try:
            yield
        finally:
            set_is_subagent(was_subagent)
            set_subagent_task_id(parent_task_id)


def release_child_run_state(task_id: str) -> None:
    """Drop what a finished child's session kept; a child that paused for approval keeps it for its resume."""
    from myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware import discard_session_loop_guard

    discard_session_loop_guard(task_id)


def extract_query_text(query: object) -> str:
    """Extract a human-readable query string from various input types."""
    from langgraph.types import Command

    if isinstance(query, Command):
        return f"Resume: {query.resume if hasattr(query, 'resume') else 'unknown'}"
    if isinstance(query, str):
        return query
    if isinstance(query, list):
        return next(
            (p.get("text", "") for p in query if isinstance(p, dict) and p.get("type") == "text"),
            "",
        )
    return str(query)


def schedule_post_run_idle_tasks(merged_context: dict[str, object]) -> None:
    """Enqueue background idle tasks after a successful agent run."""
    session_id = str(merged_context.get("session_id", ""))
    storage_root = str(merged_context.get("workspaces_storage_root", ""))

    if not (session_id and storage_root):
        return

    from myrm_agent_harness.agent.background_worker.idle_tasks import (
        run_pending_idle_tasks,
    )
    from myrm_agent_harness.agent.background_worker.idle_worker import (
        schedule_idle_task,
    )
    from myrm_agent_harness.agent.background_worker.registry import (
        get_idle_task_registry,
    )

    registry = get_idle_task_registry(storage_root)
    try:
        chat_id = str(merged_context.get("chat_id", ""))

        _fire_and_forget(registry.enqueue(session_id, "cognitive_consolidation", {}))
        if chat_id:
            _fire_and_forget(registry.enqueue(session_id, "context_compaction", {"chat_id": chat_id}))
        schedule_idle_task(
            session_id,
            lambda: run_pending_idle_tasks(session_id, registry),
            delay_seconds=60,
        )
    except Exception as exc:
        logger.error("Failed to schedule idle task for %s: %s", session_id, exc)


def init_usage_ledger(context: dict[str, object] | None) -> None:
    """Attach a ``UsageLedger`` to the current request scope."""
    if not context:
        return
    workspace_path = context.get("workspace_path")
    if not workspace_path:
        return
    try:
        from pathlib import Path

        from myrm_agent_harness.utils.token_economics.usage_ledger import UsageLedger

        session_dir = Path(str(workspace_path))
        set_usage_ledger(UsageLedger(session_dir=session_dir))
    except Exception:
        logger.debug("Failed to initialize UsageLedger", exc_info=True)


_CHECKPOINT_INCOMPATIBLE_CONTEXT_KEYS: tuple[str, ...] = (
    "goal_provider",
    "on_goal_terminal",
    "on_loop_restart",
    "on_goal_hold",
    "file_content_reader",
)


def pop_checkpoint_incompatible_merged_context(
    merged_context: dict[str, object],
) -> dict[str, object]:
    """Strip non-serializable callbacks before LangGraph checkpoint persistence."""
    stripped: dict[str, object] = {}
    for key in _CHECKPOINT_INCOMPATIBLE_CONTEXT_KEYS:
        if key in merged_context:
            stripped[key] = merged_context.pop(key)
    return stripped
