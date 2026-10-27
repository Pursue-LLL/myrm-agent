"""Unified tool interception middleware.

Orchestrates all security guards in a single interception point:

PRE-CALL:
 1. E-Stop check — global emergency brake (fail-closed)
 2. LoopGuard pre-check — tool-call loop detection
 3. Steering skip — user injected new message at runtime
 4. Invalid tool check — tool does not exist
 5. Trust attenuation — INSTALLED skills restrict dangerous tools
 5b. PII Guard — classify tool parameters for PII, block if policy requires

POST-CALL:
 6. Steering activation — check steering queue after execution
 6b. Empty output normalization — replace empty/whitespace content with "(no output)"
 7. Archive restore blocked event — emit structured GUI-safe status payloads
 7b. Mutation Verifier — track file-mutating tool outcomes for turn-end summary
 8. Context Budget Guard — truncate oversized results, track budget
 9. Context Poisoning detection — validate tool result content
10. Taint recording — propagate taint labels to session TaintTracker
10b. PII detection — classify tool result, redact PII per policy
11. LoopGuard record — record result hash for future detection
12. Verification evidence — tag bash commands containing test/lint/typecheck/build

[INPUT]
- agent.middlewares.tooling._tool_guards (POS: Pre/post-call guard orchestration)
- agent.middlewares.tooling._tool_execution_lifecycle (POS: Tool resolve, heartbeat, error handling)
- agent.middlewares.tooling._skill_failure_tracking (POS: Skill failure telemetry)
- agent.middlewares.tooling.tool_executor (POS: Tool execution engine with timeout/retry/backoff)
- agent.middlewares._session_context (POS: Middleware session context)

[OUTPUT]
- tool_interceptor_middleware: unified tool interception middleware
- SESSION_LOOP_GUARD_LIMIT: How many sessions keep a LoopGuard between run segments (least recently used dropped first)
- get_loop_guard(): Get or create the session-scoped LoopGuard (ContextVar + session-key fallback)
- reset_loop_guard(): Reset loop guard state; `is_resume=True` preserves CallRecord window and error signatures
- child_loop_guard(): A LoopGuard of its own for a nested child run, filed under its own key, restored to the parent's afterwards
- discard_session_loop_guard(): Forget the guard kept for a session that is over
- notify_loop_guard_compaction(): Reset iteration budget after context compaction

[POS]
Single interception point for all tool calls. This module is a thin
orchestrator that delegates to _tool_guards, _tool_execution_lifecycle,
and _skill_failure_tracking for the actual logic.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from langchain.agents.middleware import wrap_tool_call
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from myrm_agent_harness.agent.meta_tools.bash.bash_process_tools import (
    BASH_PROCESS_TOOL_NAME,
)
from myrm_agent_harness.agent.middlewares._session_context import (
    get_agent_id,
    get_approval_session,
    get_event_logger,
)
from myrm_agent_harness.agent.middlewares.tooling._skill_failure_tracking import (
    track_skill_execution as _track_skill_execution,
)
from myrm_agent_harness.agent.middlewares.tooling._tool_execution_lifecycle import (
    emit_tool_heartbeat,
    handle_cancellation,
    handle_execution_error,
    resolve_dynamic_tool,
)
from myrm_agent_harness.agent.middlewares.tooling._tool_guards import (
    run_post_call_guards,
    run_pre_call_guards,
)
from myrm_agent_harness.agent.middlewares.tooling.tool_executor import execute_with_retry
from myrm_agent_harness.agent.security.guards.loop_guard import LoopGuard
from myrm_agent_harness.core.context_vars import scoped_value
from myrm_agent_harness.utils.logger_utils import get_agent_logger
from myrm_agent_harness.utils.token_economics.tracker import (
    get_token_tracker,
    pop_tool_context,
    push_tool_context,
)

logger = get_agent_logger(__name__)

# How many sessions keep a guard between run segments; the completion guard bounds its per-turn state
# registry at the same size (``RUN_STATE_LIMIT``).
SESSION_LOOP_GUARD_LIMIT = 128

_loop_guard_var: ContextVar[LoopGuard | None] = ContextVar("loop_guard", default=None)
# The registry key a ``child_loop_guard`` block files its guard under; outside one, the approval session is the key.
_loop_guard_key_var: ContextVar[str | None] = ContextVar("loop_guard_key", default=None)
_session_loop_guards: dict[str, LoopGuard] = {}
_BASH_POLL_TOOLS = frozenset({BASH_PROCESS_TOOL_NAME})


def _loop_guard_session_key() -> str:
    session_key = _loop_guard_key_var.get() or get_approval_session()
    return session_key if session_key else "__default__"


def _remember_loop_guard(session_key: str, guard: LoopGuard) -> None:
    """Keep ``guard`` as the session's, newest last; past the limit the least recently used session is dropped.

    Every write to the registry goes through here, so nothing can grow it past the limit. A dropped session
    that resumes later finds no guard and starts a fresh one.
    """
    _session_loop_guards.pop(session_key, None)
    _session_loop_guards[session_key] = guard
    while len(_session_loop_guards) > SESSION_LOOP_GUARD_LIMIT:
        del _session_loop_guards[next(iter(_session_loop_guards))]


def _bind_loop_guard(guard: LoopGuard) -> LoopGuard:
    _remember_loop_guard(_loop_guard_session_key(), guard)
    _loop_guard_var.set(guard)
    return guard


def _get_session_loop_guard() -> LoopGuard | None:
    return _session_loop_guards.get(_loop_guard_session_key())


def _create_loop_guard(
    *,
    graph_recursion_limit: int = 100,
    unattended_mode: bool = False,
) -> LoopGuard:
    return LoopGuard(
        poll_tools=_BASH_POLL_TOOLS,
        graph_recursion_limit=graph_recursion_limit,
        unattended_mode=unattended_mode,
    )


def get_loop_guard() -> LoopGuard:
    """Get or create the session-scoped LoopGuard."""
    guard = _loop_guard_var.get()
    if guard is not None:
        return guard
    existing = _get_session_loop_guard()
    if existing is not None:
        return _bind_loop_guard(existing)
    return _bind_loop_guard(_create_loop_guard())


def clear_all_session_loop_guards_for_tests() -> None:
    """Drop every cached session guard and the bound guard (test isolation only).

    The cache is a module global keyed by session id, and the bound guard lives in a
    ContextVar that outlives a test inside the same event loop. A guard that spent its
    iteration budget in one test is otherwise handed to the next test, which then fails
    with a stuck-tool interrupt instead of its own run.
    """
    _session_loop_guards.clear()
    _loop_guard_var.set(None)


def reset_loop_guard(
    *,
    is_resume: bool = False,
    graph_recursion_limit: int = 100,
    unattended_mode: bool = False,
) -> None:
    """Reset the session-scoped loop guard state.

    Called at the start of each agent run and at each Goal continuation turn.
    When *is_resume* is True, error signatures are preserved so that the same
    class of failures still counts toward the budget.  *graph_recursion_limit*
    is forwarded to ``LoopGuard._configure_budget`` to keep budget thresholds
    aligned with the actual LangGraph recursion limit.
    """
    guard = _loop_guard_var.get()
    if guard is None:
        guard = _get_session_loop_guard()
    if guard is None:
        _bind_loop_guard(
            _create_loop_guard(graph_recursion_limit=graph_recursion_limit, unattended_mode=unattended_mode)
        )
        return
    guard.reset(
        preserve_error_signatures=is_resume,
        preserve_call_window=is_resume,
    )
    guard.unattended_mode = unattended_mode
    guard._configure_budget(graph_recursion_limit)
    _bind_loop_guard(guard)


@contextmanager
def child_loop_guard(session_key: str) -> Iterator[LoopGuard]:
    """Give a nested child run a LoopGuard of its own, filed under ``session_key``, for the ``with`` block.

    A run resets the guard it finds when it starts, so a child sharing its parent's would erase the parent's
    tool-call history. The guard stays in the session registry under ``session_key`` so a resume of the same
    child finds it again. Inside the block that key is where every binding of the guard files it, whichever
    approval session the child's run was started under, so a child dispatched under its parent's session
    never takes over the parent's registry slot.
    """
    guard = _session_loop_guards.get(session_key)
    if guard is None:
        guard = _create_loop_guard()
    _remember_loop_guard(session_key, guard)
    with scoped_value(_loop_guard_var, guard), scoped_value(_loop_guard_key_var, session_key):
        yield guard


def discard_session_loop_guard(session_key: str) -> None:
    """Forget the guard kept for a session that is over, such as a child that finished."""
    _session_loop_guards.pop(session_key, None)


def notify_loop_guard_compaction() -> None:
    """Notify the loop guard that context compaction occurred.

    Resets the iteration budget counter so the agent is not prematurely
    terminated after compaction.  Error signatures are preserved so that
    recurring failures are still tracked across compaction boundaries.
    """
    try:
        guard = _loop_guard_var.get()
    except LookupError:
        return
    if guard is None:
        guard = _get_session_loop_guard()
    if guard is None:
        return
    prev_calls = guard._metrics.total_calls
    guard.notify_compaction()
    if prev_calls > 0:
        logger.debug("LoopGuard compaction reset: total_calls %d → 0", prev_calls)


# ---------------------------------------------------------------------------
# Main middleware entry point
# ---------------------------------------------------------------------------


@wrap_tool_call
async def tool_interceptor_middleware(
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[object]]],
) -> ToolMessage | Command[object]:
    """Unified tool interception middleware with metrics collection."""
    tool_name = request.tool_call.get("name", "unknown")
    call_id = request.tool_call.get("id")

    from myrm_agent_harness.infra.tracing.gen_ai import execute_tool_span

    with execute_tool_span(
        name=tool_name,
        call_id=str(call_id) if call_id else None,
        arguments=_get_tool_args(request),
    ) as span:
        try:
            result = await _tool_interceptor_middleware_inner(request, handler)

            status = "success"
            error_message = ""
            error_category: str | None = None
            loop_kind: str | None = None
            if hasattr(result, "status") and result.status == "error":
                status = "error"
                error_message = getattr(result, "content", "")
                error_category, loop_kind = _extract_failure_metadata(result)
                span.mark_error(error_category or "tool_error")
            else:
                span.record_result(getattr(result, "content", ""))

            from myrm_agent_harness.observability.metrics.registry import (
                metrics_registry,
            )

            agent_id_for_metrics = get_agent_id() or "base_agent"

            if metrics_registry.enabled:
                metrics_registry.record_tool_call(agent_id=agent_id_for_metrics, tool_name=tool_name, status=status)

            _track_skill_execution(
                tool_name,
                tool_call_id=str(request.tool_call.get("id", "")),
                tool_args=_get_tool_args(request),
                success=(status == "success"),
                error_message=error_message,
                error_category=error_category,
                loop_kind=loop_kind,
            )
            return result

        except Exception as e:
            from myrm_agent_harness.observability.metrics.registry import (
                metrics_registry,
            )

            agent_id_for_metrics = get_agent_id() or "base_agent"

            if metrics_registry.enabled:
                metrics_registry.record_tool_call(agent_id=agent_id_for_metrics, tool_name=tool_name, status="error")

            _track_skill_execution(
                tool_name,
                tool_call_id=str(request.tool_call.get("id", "")),
                tool_args=_get_tool_args(request),
                success=False,
                error_message=str(e),
                error_category=None,
                loop_kind=_loop_kind_from_exception(e),
            )
            raise


def _get_tool_args(request: ToolCallRequest) -> dict[str, object]:
    raw_args = request.tool_call.get("args") or {}
    return raw_args if isinstance(raw_args, dict) else {}


def _extract_failure_metadata(
    result: ToolMessage | Command[object],
) -> tuple[str | None, str | None]:
    if not isinstance(result, ToolMessage):
        return None, None
    raw_category = result.additional_kwargs.get("error_category")
    raw_loop_kind = result.additional_kwargs.get("loop_kind")
    error_category = raw_category if isinstance(raw_category, str) else None
    loop_kind = raw_loop_kind if isinstance(raw_loop_kind, str) else None
    return error_category, loop_kind


def _loop_kind_from_exception(exc: Exception) -> str | None:
    if type(exc).__name__ != "ToolStuckException":
        return None
    try:
        return get_loop_guard().last_detection_kind
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Inner orchestration
# ---------------------------------------------------------------------------


async def _tool_interceptor_middleware_inner(
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[object]]],
) -> ToolMessage | Command[object]:
    """Core orchestration: pre-guards -> execute -> post-guards."""
    request = resolve_dynamic_tool(request)
    tool_name = request.tool_call.get("name", "unknown")
    tool_call_id = request.tool_call.get("id") or ""
    tool_args: dict[str, object] = request.tool_call.get("args") or {}

    pre_result = await run_pre_call_guards(request, tool_name, tool_call_id, tool_args, get_loop_guard)
    if isinstance(pre_result, ToolMessage):
        return pre_result

    push_tool_context(tool_name)

    token_tracker = get_token_tracker()
    token_snapshot = 0
    if token_tracker and tool_name in token_tracker.tool_usage:
        token_snapshot = token_tracker.tool_usage[tool_name].total_tokens

    start_time = time.time()

    heartbeat_task = asyncio.create_task(emit_tool_heartbeat(tool_name, tool_call_id, start_time))

    try:
        from myrm_agent_harness.agent.middlewares._session_context import (
            get_allowed_domains_map,
        )

        allowed_domains = get_allowed_domains_map().get(tool_name)

        while True:
            try:
                result = await execute_with_retry(request, handler, tool_name, tool_call_id, allowed_domains)
                break
            except Exception as e:
                if type(e).__name__ == "ToolClarificationError":
                    from langgraph.types import interrupt

                    payload = {
                        "action_type": "tool_clarification",
                        "tool_name": tool_name,
                        "tool_call_id": tool_call_id,
                        "error_message": str(e),
                        "payload": request.tool_call.get("args") or {},
                    }
                    resume_value = interrupt(payload)

                    if isinstance(resume_value, dict):
                        decision = resume_value
                    else:
                        decision = {}

                    if decision.get("type") == "approve" or decision.get("action") == "approve":
                        if decision.get("edited_payload"):
                            new_args = decision["edited_payload"]
                            request.tool_call["args"] = new_args
                        logger.info("Resuming tool %s with new args", tool_name)
                        continue
                    else:
                        break
                else:
                    raise e

        result = await run_post_call_guards(
            result,
            tool_name,
            tool_call_id,
            tool_args,
            pre_result.loop_guard,
            pre_result.loop_verdict,
            pre_result.freq_guard,
            pre_result.freq_verdict,
            pre_result.steering_token,
        )
        return result

    except asyncio.CancelledError as e:
        return await handle_cancellation(e, tool_name, tool_call_id, tool_args, start_time)

    except Exception as e:
        return await handle_execution_error(e, tool_name, tool_call_id, tool_args)

    finally:
        heartbeat_task.cancel()
        import contextlib

        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task

        if token_tracker and tool_name in token_tracker.tool_usage:
            current_tokens = token_tracker.tool_usage[tool_name].total_tokens
            delta_tokens = current_tokens - token_snapshot
            if delta_tokens > 0:
                event_logger = get_event_logger()
                if event_logger is not None:
                    await event_logger.log(
                        "tool_token_usage",
                        {"tool_name": tool_name, "tokens": delta_tokens},
                    )
        pop_tool_context()
