"""摘要调用守卫：进度感知的空闲超时、总上限与取消安全清理。

[INPUT]
- langchain_core.messages::BaseMessage (POS: 消息类型)
- agent.context_management.infra.schemas::ContextConfig / StructuredSummary (POS: 配置与摘要类型)
- agent.context_management.strategies.summary.progress_timeout (POS: 进度时钟与超时异常)
- agent.context_management.strategies.summary.summarizer::generate_structured_summary (POS: LLM 摘要生成)

[OUTPUT]
- _guarded_summarize: 带双重超时与前端进度事件的摘要调用

[POS]
`summarize_processor/` 的超时与取消保护层。
"""

from __future__ import annotations

import asyncio
import contextlib
import time

from langchain_core.messages import BaseMessage

from ....infra.schemas import ContextConfig, StructuredSummary
from ....strategies.summary.progress_timeout import (
    InactivityTimeoutError,
    ProgressClock,
    TotalCeilingTimeoutError,
)
from ....strategies.summary.summarizer import generate_structured_summary


async def _guarded_summarize(
    messages: list[BaseMessage],
    llm: object,
    chat_id: str | None,
    config: ContextConfig,
    focus_topic: str,
    pre_compact_message: BaseMessage | None,
    runnable_config: object | None = None,
) -> tuple[list[BaseMessage], StructuredSummary]:
    """Wrap generate_structured_summary with inactivity + total ceiling timeouts.

    Monitors streaming progress via _DefaultProgressTracker. If the LLM call
    stalls (no token for inactivity_timeout) or exceeds total ceiling, raises
    InactivityTimeoutError / TotalCeilingTimeoutError which the caller converts
    to a deterministic fallback.

    Emits `context_compaction` lifecycle events via dispatch_custom_event for
    frontend progress display (debounced: only after 3s to avoid flashing).
    """
    from myrm_agent_harness.utils.event_utils import dispatch_custom_event

    inactivity_s = config.compaction_inactivity_timeout_s
    ceiling_s = config.compaction_total_ceiling_s
    tracker = ProgressClock()
    _DEBOUNCE_SECONDS = 3.0  # noqa: N806  # constant within closure scope

    async def _emit_compaction_event(phase: str, elapsed_s: float = 0, **extra: object) -> None:
        """Emit a context_compaction event to the frontend (best-effort, never throws)."""
        try:
            payload: dict[str, object] = {
                "step_key": "context_compaction",
                "phase": phase,
                "elapsed_s": round(elapsed_s, 1),
            }
            payload.update(extra)
            await dispatch_custom_event("agent_status", payload, config=runnable_config)  # type: ignore[arg-type]
        except Exception:
            pass

    async def _watchdog() -> None:
        """Background coroutine that checks tracker liveness periodically."""
        start = time.monotonic()
        check_interval = min(inactivity_s / 3, 10.0)
        debounce_emitted = False
        while True:
            await asyncio.sleep(check_interval)
            elapsed = time.monotonic() - start
            if elapsed >= ceiling_s:
                await _emit_compaction_event("timeout", elapsed_s=elapsed, reason="ceiling")
                raise TotalCeilingTimeoutError(elapsed)
            idle = tracker.seconds_since_last_touch
            if idle >= inactivity_s:
                await _emit_compaction_event("timeout", elapsed_s=elapsed, reason="inactivity")
                raise InactivityTimeoutError(idle)
            if not debounce_emitted and elapsed >= _DEBOUNCE_SECONDS:
                debounce_emitted = True
                await _emit_compaction_event("active", elapsed_s=elapsed)
            elif debounce_emitted:
                await _emit_compaction_event("active", elapsed_s=elapsed)

    async def _summarize() -> tuple[list[BaseMessage], StructuredSummary]:
        return await generate_structured_summary(
            messages=messages,
            llm=llm,  # type: ignore[arg-type]
            chat_id=chat_id,
            config=config,
            focus_topic=focus_topic,
            pre_compact_message=pre_compact_message,
            progress_tracker=tracker,
        )

    summarize_task = asyncio.ensure_future(_summarize())
    watchdog_task = asyncio.ensure_future(_watchdog())

    try:
        done, pending = await asyncio.wait(
            {summarize_task, watchdog_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

        for task in done:
            exc = task.exception()
            if exc is not None:
                raise exc
            if task is summarize_task:
                return task.result()

        raise RuntimeError("Unexpected: no task completed with result")
    except (InactivityTimeoutError, TotalCeilingTimeoutError):
        raise
    finally:
        # Ensure tasks are cleaned up on ALL exit paths (including external CancelledError)
        for task in (summarize_task, watchdog_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(summarize_task, watchdog_task, return_exceptions=True)
