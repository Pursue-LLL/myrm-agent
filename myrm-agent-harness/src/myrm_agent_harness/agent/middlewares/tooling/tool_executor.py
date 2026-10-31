"""Tool Executor with Timeout and Retry

[INPUT]
- langchain_core.messages::ToolMessage (POS: Core message type definitions)
- langchain.agents.middleware::ToolCallRequest
- langgraph.types::Command
- agent.middlewares.tooling._tool_helpers (POS: Stateless helper functions for tool_interceptor_middleware)
- agent.middlewares._session_context (POS: Middleware session context)
- agent.streaming.types::AgentEventType (POS: Agent event type definitions)
- utils.errors::ToolError (POS: Framework-level tool errors)
- agent.middlewares.tooling._tool_execution_lifecycle::report_tool_cancelled (POS: hook + stream event + result for a cancelled tool call)
- utils.runtime.cancel_hook::DeadlineCut, cut_deadline_on_cancel (POS: end a timeout scope when the request token is cancelled)
- utils.runtime.cancellation::get_cancel_token (POS: request-level cancellation token; a stopped request is never retried)

[OUTPUT]
- execute_with_retry(): Execute a tool call with timeout, retry, and exponential backoff

[POS]
Tool execution engine. Encapsulates timeout/retry/backoff logic with event logging
and stream emission. Called from tool_interceptor_middleware after pre-call guards pass.
A request that was stopped meanwhile ends the backoff at once and gets no retry: a retry would run again a call
the user already stopped. The stop also ends a call that is still running: a tool that reacts to the stop returns its
own result within the grace period, any other (a remote call that only looks at its deadline) is cancelled when the
period ends, so no call keeps running after the request is over.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from myrm_agent_harness.agent.middlewares._session_context import (
    get_event_logger,
    get_terminal_errors,
)
from myrm_agent_harness.agent.middlewares.tooling._tool_execution_lifecycle import report_tool_cancelled
from myrm_agent_harness.agent.middlewares.tooling._tool_helpers import (
    format_tool_error,
    get_tool_timeout,
    is_non_retryable,
    make_error_msg,
)
from myrm_agent_harness.core.security.redact import redact_sensitive_text
from myrm_agent_harness.utils.errors import ToolError, ToolErrorCategory
from myrm_agent_harness.utils.logger_utils import get_agent_logger
from myrm_agent_harness.utils.runtime.cancel_hook import DeadlineCut, cut_deadline_on_cancel
from myrm_agent_harness.utils.runtime.cancellation import CancelReason, get_cancel_token

logger = get_agent_logger(__name__)

_STOP_POLL_S = 0.25
# How long a call that is already ending itself on the stop may take to hand back its result before the gate cancels it.
# It has to outlast the slowest cleanup such a call performs, because a second cancel arriving mid-cleanup abandons it:
# a shell that ignores SIGTERM is killed after two 2s grace periods, a wedged browser tab is healed in about a second.
# A call that does not react to the stop (a remote call) is cancelled only when this period is over.
_STOP_GRACE_S = 5.0


def _stop_reason() -> str:
    """The stream-event vocabulary for why the request was stopped."""
    token = get_cancel_token()
    reason = token.cancel_reason if token is not None else None
    if reason == CancelReason.TIMEOUT:
        return "timeout"
    if reason == CancelReason.DISCONNECT:
        return "session_ended"
    return "user_cancelled"


def _request_stopped() -> bool:
    token = get_cancel_token()
    return token is not None and token.is_cancelled


async def _backoff_sleep(seconds: float) -> None:
    """Wait before a retry, ending early once the request is stopped (the caller then skips the retry)."""
    if get_cancel_token() is None:
        await asyncio.sleep(seconds)
        return
    remaining = seconds
    while remaining > 0 and not _request_stopped():
        step = min(_STOP_POLL_S, remaining)
        await asyncio.sleep(step)
        remaining -= step


async def execute_with_retry(
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[object]]],
    tool_name: str,
    tool_call_id: str,
    allowed_domains: list[str] | None,
) -> ToolMessage | Command[object]:
    """Execute a tool call with timeout, retry (max 2 attempts), and exponential backoff.

    Handles:
    - Timeout with event logging and stream emission
    - Retryable vs non-retryable error classification
    - Exponential backoff with jitter
    - Terminal error circuit breaker registration
    """
    from myrm_agent_harness.core.security.guards.url_allowlist import URLAllowlistGuard
    from myrm_agent_harness.observability.metrics.agent_metrics import (
        record_ttfa_first_action,
        tool_execution_failed_total,
        tool_execution_total,
    )

    record_ttfa_first_action()
    if tool_execution_total is not None:
        tool_execution_total.labels(tool_name=tool_name).inc()

    tool_call = getattr(request, "tool_call", None)
    tool_args = tool_call.get("args") if isinstance(tool_call, dict) else None
    timeout = get_tool_timeout(tool_name, tool_args)
    error_history: list[dict[str, Any]] = []
    start_time = time.time()

    for attempt in range(2):
        if attempt > 0 and _request_stopped():
            return make_error_msg(
                tool_name,
                tool_call_id,
                f"{tool_name} was cancelled (request stopped) and not retried.",
                error_category=ToolErrorCategory.TOOL_CANCELLED,
            )
        stop_cut = DeadlineCut()
        try:
            async with (
                asyncio.timeout(timeout) as deadline,
                cut_deadline_on_cancel(get_cancel_token(), deadline, stop_cut, grace_s=_STOP_GRACE_S),
            ):
                with URLAllowlistGuard.apply(allowed_domains):
                    result = await handler(request)

                if attempt == 0:
                    from myrm_agent_harness.agent.middlewares.tooling._tool_helpers import (
                        check_semantic_failure_retryable,
                    )

                    raw_res = result.content if isinstance(result, ToolMessage) else result
                    is_retryable, reason = check_semantic_failure_retryable(
                        raw_res,
                        tool_name,
                        tool_args=tool_args if isinstance(tool_args, dict) else None,
                    )
                    if is_retryable:
                        elapsed = (time.time() - start_time) * 1000
                        error_history.append(
                            {
                                "attempt": attempt + 1,
                                "error": f"SemanticRetryableFailure: {reason}",
                                "elapsed_ms": elapsed,
                            }
                        )
                        event_logger = get_event_logger()
                        if event_logger is not None:
                            await event_logger.log(
                                "TOOL_RETRY",
                                {
                                    "tool_name": tool_name,
                                    "attempt": attempt + 2,
                                    "reason": f"semantic_retryable:{reason}",
                                },
                            )
                        backoff = min(2**attempt + random.uniform(0, 1), 5.0)
                        logger.warning(
                            "Transient business error [%s] attempt %d/2: %s, retry in %.1fs",
                            tool_name,
                            attempt + 1,
                            reason,
                            backoff,
                        )
                        await _emit_retry_event(tool_name, attempt, backoff)
                        await _backoff_sleep(backoff)
                        continue

                return result
        except TimeoutError as e:
            if stop_cut.by_cancel:
                return await report_tool_cancelled(
                    tool_name,
                    tool_call_id,
                    tool_args if isinstance(tool_args, dict) else {},
                    start_time,
                    _stop_reason(),
                )
            elapsed = (time.time() - start_time) * 1000
            error_history.append(
                {
                    "attempt": attempt + 1,
                    "error": f"TimeoutError after {timeout}s",
                    "elapsed_ms": elapsed,
                }
            )

            event_logger = get_event_logger()
            if event_logger is not None:
                await event_logger.log(
                    "TOOL_TIMEOUT",
                    {
                        "tool_name": tool_name,
                        "timeout_seconds": timeout,
                        "attempt": attempt + 1,
                        "elapsed_ms": elapsed,
                    },
                )

            await _emit_timeout_event(tool_name, timeout, attempt, elapsed)

            if attempt < 1:
                if event_logger is not None:
                    await event_logger.log(
                        "TOOL_RETRY",
                        {
                            "tool_name": tool_name,
                            "attempt": attempt + 2,
                            "reason": "timeout",
                        },
                    )
                backoff = min(2**attempt + random.uniform(0, 1), 10.0)
                logger.warning(f" Timeout [{tool_name}] attempt {attempt + 1}/2, retry in {backoff:.1f}s")
                await _emit_retry_event(tool_name, attempt, backoff)
                await _backoff_sleep(backoff)
            else:
                total_duration = time.time() - start_time
                error_msg = f"{tool_name} execution timed out after {attempt + 1} attempts"
                user_hint = (
                    f"Timeout after {timeout}s. Tried {attempt + 1} times over {total_duration:.1f}s. "
                    "Try reducing data size or splitting the task."
                )
                logger.error("Tool timeout final failure [%s]: %s", tool_name, error_msg)
                if tool_execution_failed_total is not None:
                    tool_execution_failed_total.labels(tool_name=tool_name, error_type="timeout").inc()
                raise ToolError(
                    message=error_msg,
                    user_hint=user_hint,
                    diagnostic_info={
                        "retry_count": attempt,
                        "total_duration_seconds": total_duration,
                        "timeout_seconds": timeout,
                        "error_history": error_history,
                    },
                    error_code="TIMEOUT_MAX_RETRIES",
                ) from e

        except Exception as e:
            from langgraph.errors import GraphInterrupt

            if isinstance(e, (GraphInterrupt, InterruptedError)):
                raise

            if is_non_retryable(e, tool_name) or attempt == 1:
                if error_history:
                    total_duration = time.time() - start_time
                    error_msg = f"{tool_name} execution failed after {attempt + 1} attempts"
                    original_hint = getattr(e, "user_hint", "") if isinstance(e, ToolError) else ""
                    user_hint = f"Tried {attempt + 1} times over {total_duration:.1f}s. {original_hint}"
                    logger.error(f" Tool execution final failure [{tool_name}]: {error_msg}")
                    if tool_execution_failed_total is not None:
                        tool_execution_failed_total.labels(tool_name=tool_name, error_type=type(e).__name__).inc()
                    safe_orig_error = redact_sensitive_text(f"{type(e).__name__}: {str(e)[:200]}")
                    raise ToolError(
                        message=error_msg,
                        user_hint=user_hint,
                        diagnostic_info={
                            "retry_count": attempt,
                            "total_duration_seconds": total_duration,
                            "error_history": error_history,
                            "original_error": safe_orig_error,
                        },
                        error_code="MAX_RETRIES_EXCEEDED",
                    ) from e

                if isinstance(e, ToolError):
                    category = e.error_category
                    hint = e.user_hint or None
                    if category in ("network_blocked", "sandbox_ro"):
                        get_terminal_errors().add(category)
                        logger.info(f" Circuit breaker registered terminal error: {category}")
                    if tool_execution_failed_total is not None:
                        tool_execution_failed_total.labels(
                            tool_name=tool_name, error_type=category or "tool_error"
                        ).inc()
                    return make_error_msg(
                        tool_name,
                        tool_call_id,
                        format_tool_error(e, tool_name),
                        error_category=category,
                        error_hint=hint,
                    )
                raise

            elapsed = (time.time() - start_time) * 1000
            safe_err_text = redact_sensitive_text(f"{type(e).__name__}: {str(e)[:200]}")
            error_history.append(
                {
                    "attempt": attempt + 1,
                    "error": safe_err_text,
                    "elapsed_ms": elapsed,
                }
            )

            event_logger = get_event_logger()
            if event_logger is not None:
                await event_logger.log(
                    "TOOL_RETRY",
                    {
                        "tool_name": tool_name,
                        "attempt": attempt + 2,
                        "reason": f"{type(e).__name__}",
                        "error": safe_err_text,
                    },
                )

            retry_after = None
            response = getattr(e, "response", None)
            if response is not None:
                headers = getattr(response, "headers", {})
                # Some clients use case-insensitive dicts, but just in case check both
                retry_val = headers.get("retry-after") or headers.get("Retry-After")
                if retry_val is not None:
                    with contextlib.suppress(ValueError):
                        retry_after = float(retry_val)

            if retry_after is not None:
                backoff = min(retry_after + random.uniform(0, 1), 60.0)
                logger.warning(
                    f" Rate limit [{tool_name}] respects retry-after: {retry_after}s, retry in {backoff:.1f}s"
                )
            else:
                backoff = min(2**attempt + random.uniform(0, 1), 10.0)
                logger.warning(
                    f" Error [{tool_name}] {type(e).__name__}: {redact_sensitive_text(str(e)[:100])}, retry in {backoff:.1f}s"
                )

            await _backoff_sleep(backoff)

    raise RuntimeError(f"Unexpected: execute_with_retry loop completed without return for {tool_name}")


async def _emit_timeout_event(tool_name: str, timeout: float, attempt: int, elapsed: float) -> None:
    """Emit TOOL_TIMEOUT to stream for real-time visibility."""
    try:
        from myrm_agent_harness.agent.streaming.types import AgentEventType
        from myrm_agent_harness.utils.runtime.progress_sink import (
            get_tool_progress_sink,
        )

        sink = get_tool_progress_sink()
        if sink:
            await sink.emit(
                {
                    "type": AgentEventType.TOOL_TIMEOUT.value,
                    "data": {
                        "tool_name": tool_name,
                        "timeout_seconds": timeout,
                        "attempt": attempt + 1,
                        "elapsed_ms": int(elapsed),
                    },
                }
            )
    except Exception as exc:
        logger.debug("Failed to emit TOOL_TIMEOUT event: %s", exc)


async def _emit_retry_event(tool_name: str, attempt: int, backoff: float) -> None:
    """Emit TOOL_RETRY to stream for real-time visibility."""
    try:
        from myrm_agent_harness.agent.streaming.types import AgentEventType
        from myrm_agent_harness.utils.runtime.progress_sink import (
            get_tool_progress_sink,
        )

        sink = get_tool_progress_sink()
        if sink:
            step_data = {
                "tool_name": tool_name,
                "attempt": attempt + 2,
                "max_attempts": 2,
                "reason": "timeout",
                "backoff_seconds": backoff,
            }
            await sink.emit(
                {
                    "type": AgentEventType.TOOL_RETRY.value,
                    "data": step_data,
                }
            )
    except Exception as exc:
        logger.warning("Failed to emit TOOL_RETRY event: %s", exc)
