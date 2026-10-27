"""SubagentExecutor retry loop.

[INPUT]
- .executor_attempt_mixin::SubagentExecutorAttemptMixin (POS: One child-agent run attempt including fork context and result post-processing.)
- .executor_helpers::_cascade_cancel_descendants, _compact_error_message, read_partial_output (POS: Pure helper functions for SubagentExecutor mixins and external callers.)
- .types::SubagentBudgetExceededError, SubagentConfig, SubAgentResult, SubAgentStatus (POS: Subagent subsystem core type definitions.)
- toolkits.llms.errors.exceptions::MyrmLLMError (POS: Standardized LLM Error thrown by the Harness framework.)
- agent.hooks.executor::fire_hook (POS: Hook execution layer. Manages hook registration and execution with ContextVar-based session isolation.)

[OUTPUT]
- SubagentExecutorRetryMixin.run_with_retry: every run (any attempt result status, timeout, LLM error, budget, other error, no attempt, cancellation) closes with SUBAGENT_STOP, paired with SUBAGENT_START; a single cancellation landing during STOP delivery sends a final STOP with status=cancelled, while a second cancellation landing inside the cancel path's own hook delivery ends the run with CancelledError and no STOP

[POS]
Retry loop with hooks and graceful cancellation.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool

from myrm_agent_harness.agent.security.guards.taint_tracker import get_taint_tracker
from myrm_agent_harness.toolkits.llms.errors.exceptions import MyrmLLMError
from myrm_agent_harness.utils.logger_utils import get_agent_logger
from myrm_agent_harness.utils.runtime.progress_sink import ToolProgressSink
from myrm_agent_harness.utils.runtime.steering import SteeringToken
from myrm_agent_harness.utils.token_economics.tracker import get_token_tracker

from .executor_attempt_mixin import SubagentExecutorAttemptMixin
from .executor_helpers import (
    _cascade_cancel_descendants,
    _compact_error_message,
    read_partial_output,
)
from .types import (
    SubagentBudgetExceededError,
    SubagentConfig,
    SubAgentResult,
    SubAgentStatus,
)

if TYPE_CHECKING:
    from myrm_agent_harness.agent.base_agent import BaseAgent
    from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

logger = get_agent_logger(__name__)


class SubagentExecutorRetryMixin(SubagentExecutorAttemptMixin):
    """Run subagents with retries."""

    async def run_with_retry(
        self,
        task_id: str,
        agent_type: str,
        task_description: str,
        config: SubagentConfig,
        context: dict[str, object],
        tool_registry_getter: Callable[[], list[BaseTool]],
        start_time: float,
        parent_agent: BaseAgent,
        cancel_flags: dict[str, bool],
        children_agents: dict[str, BaseAgent],
        children_steering: dict[str, SteeringToken],
        trace_id: str = "",
        steering_token: SteeringToken | None = None,
        cancel_token: CancellationToken | None = None,
        resume_command: object | None = None,
        parent_progress_sink: ToolProgressSink | None = None,
        complexity_tier: str | None = None,
        on_running_token_usage: Callable[[dict[str, object]], None] | None = None,
        internal: bool = False,
    ) -> SubAgentResult:
        """Execute subagent with retry logic."""
        retries_left = config.max_retries
        backoff_seconds = config.retry_backoff_seconds
        # A failed attempt's streamed text is the parent's tool result: twice the error budget at most.
        partial_budget = config.max_error_chars * 2

        if steering_token is None:
            steering_token = SteeringToken()
            children_steering[task_id] = steering_token

        context = await self._inherit_parent_context(context, task_id, parent_agent)
        context["trace_id"] = trace_id

        from myrm_agent_harness.agent.hooks.executor import fire_hook
        from myrm_agent_harness.agent.hooks.types import HookEvent

        await fire_hook(
            HookEvent.SUBAGENT_START,
            {
                "task_id": task_id,
                "agent_type": agent_type,
                "task_description": task_description,
                "trace_id": trace_id,
            },
        )

        parent_tracker = get_token_tracker()
        parent_taint = get_taint_tracker()

        async def close_run(outcome: SubAgentResult) -> SubAgentResult:
            """Fire SUBAGENT_STOP for the run's outcome; every return goes through here.

            Hooks are awaited one by one, so a cancellation can land while the STOP is still being delivered. The
            cancel path then delivers its own STOP, so a single cancellation leaves every subscriber with at least
            one STOP and the last one carries the run's final status. A second cancellation landing while the cancel
            path is delivering its own hooks propagates and leaves no STOP.
            """
            payload: dict[str, object] = {
                "task_id": task_id,
                "agent_type": agent_type,
                "success": outcome.success,
                "status": outcome.status.value,
                "duration_seconds": outcome.duration_seconds,
                "trace_id": trace_id,
            }
            if outcome.success:
                payload["result"] = outcome.result
            else:
                payload["error"] = outcome.error
            await fire_hook(HookEvent.SUBAGENT_STOP, payload)
            return outcome

        async def finish_failed(status: SubAgentStatus, error: str, partial: str = "") -> SubAgentResult:
            """Close the run with an unsuccessful outcome: failure, timeout, budget or cancellation."""
            now = time.time()
            return await close_run(
                SubAgentResult(
                    success=False,
                    task_id=task_id,
                    agent_type=agent_type,
                    result=partial,
                    error=error,
                    duration_seconds=now - start_time,
                    completed_at=now,
                    status=status,
                    trace_id=trace_id,
                )
            )

        try:
            while retries_left > 0:
                try:
                    result = await self._run_single_attempt(
                        task_id,
                        agent_type,
                        task_description,
                        config,
                        context,
                        tool_registry_getter,
                        start_time,
                        parent_tracker,
                        parent_taint,
                        parent_agent,
                        cancel_flags,
                        children_agents,
                        fire_hook,
                        HookEvent,
                        trace_id,
                        steering_token,
                        cancel_token=cancel_token,
                        resume_command=resume_command,
                        parent_progress_sink=parent_progress_sink,
                        on_running_token_usage=on_running_token_usage,
                        internal=internal,
                    )
                    await close_run(result)
                    return result
                except TimeoutError as timeout_exc:
                    retries_left -= 1
                    logger.warning("[subagent:%s] Timeout, retries_left=%d", task_id, retries_left)
                    if retries_left > 0:
                        await asyncio.sleep(backoff_seconds)
                        backoff_seconds *= 2
                        continue
                    return await finish_failed(
                        SubAgentStatus.TIMED_OUT,
                        (
                            f"Timeout after {config.timeout_seconds}s"
                            if config.timeout_seconds is not None
                            else "Timeout"
                        ),
                        read_partial_output(timeout_exc, partial_budget),
                    )
                except MyrmLLMError as llm_exc:
                    retries_left -= 1
                    logger.warning(
                        "[subagent:%s] LLM error, retries_left=%d",
                        task_id,
                        retries_left,
                    )
                    if retries_left > 0:
                        await asyncio.sleep(backoff_seconds)
                        backoff_seconds *= 2
                        continue
                    return await finish_failed(
                        SubAgentStatus.FAILED,
                        _compact_error_message(str(llm_exc), config.max_error_chars),
                        read_partial_output(llm_exc, partial_budget),
                    )
                except SubagentBudgetExceededError as error:
                    return await finish_failed(
                        SubAgentStatus.CANCELLED_BY_BUDGET,
                        str(error),
                        read_partial_output(error, partial_budget),
                    )
                except Exception as error:
                    retries_left -= 1
                    logger.error(
                        "[subagent:%s] Error: %s, retries_left=%d",
                        task_id,
                        error,
                        retries_left,
                        exc_info=True,
                    )
                    if retries_left > 0:
                        await asyncio.sleep(backoff_seconds)
                        backoff_seconds *= 2
                        continue
                    return await finish_failed(
                        SubAgentStatus.FAILED,
                        _compact_error_message(f"{type(error).__name__}: {error}", config.max_error_chars),
                        read_partial_output(error, partial_budget),
                    )

            return await finish_failed(SubAgentStatus.FAILED, "Max retries exceeded")

        except asyncio.CancelledError:
            logger.info("[subagent:%s] Cancelled, executing graceful shutdown", task_id)
            _cascade_cancel_descendants(children_agents.get(task_id))
            now = time.time()
            await fire_hook(
                HookEvent.SUBAGENT_CANCEL_COMPLETE,
                {
                    "task_id": task_id,
                    "agent_type": agent_type,
                    "duration_seconds": now - start_time,
                    "trace_id": trace_id,
                },
            )
            return await finish_failed(SubAgentStatus.CANCELLED, "Cancelled")
        finally:
            logger.debug("[subagent:%s] Resource cleanup complete", task_id)
