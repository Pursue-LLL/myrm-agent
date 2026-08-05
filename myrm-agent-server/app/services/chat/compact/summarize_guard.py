"""Progress-aware timeout guard for compact summarize.

[INPUT]
- myrm_agent_harness...generate_structured_summary (POS: harness summarize SSOT)
- compact._constants::COMPACT_INACTIVITY_TIMEOUT_S, COMPACT_TOTAL_CEILING_S (POS: timeout bounds)

[OUTPUT]
- guarded_compact_summarize: progress-aware wrapper for API / idle compact paths

[POS]
Server-side summarize timeout guard; keeps long compactions from hanging Web turns.
"""

from __future__ import annotations

import asyncio
import logging
import time as time_module

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage

from app.services.chat.compact._constants import (
    COMPACT_INACTIVITY_TIMEOUT_S,
    COMPACT_TOTAL_CEILING_S,
)

logger = logging.getLogger(__name__)


async def guarded_compact_summarize(
    lc_messages: list[BaseMessage],
    llm: BaseChatModel,
    chat_id: str,
    existing_summary: object | None,
    focus_topic: str,
    max_context_tokens: int = 128000,
) -> tuple[list[BaseMessage], object]:
    """Wrap generate_structured_summary with progress-aware timeout for the API path."""
    from myrm_agent_harness.agent.context_management.infra.schemas import ContextConfig
    from myrm_agent_harness.agent.context_management.strategies.progress_timeout import (
        InactivityTimeoutError,
        ProgressClock,
        TotalCeilingTimeoutError,
    )
    from myrm_agent_harness.agent.context_management.strategies.summarizer import (
        generate_structured_summary,
    )

    tracker = ProgressClock()
    config = ContextConfig(max_context_tokens=max_context_tokens)

    async def _watchdog() -> None:
        start = time_module.monotonic()
        check_interval = min(COMPACT_INACTIVITY_TIMEOUT_S / 3, 10.0)
        while True:
            await asyncio.sleep(check_interval)
            elapsed = time_module.monotonic() - start
            if elapsed >= COMPACT_TOTAL_CEILING_S:
                raise TotalCeilingTimeoutError(elapsed)
            idle = tracker.seconds_since_last_touch
            if idle >= COMPACT_INACTIVITY_TIMEOUT_S:
                raise InactivityTimeoutError(idle)

    async def _summarize() -> tuple[list[BaseMessage], object]:
        return await generate_structured_summary(
            messages=lc_messages,
            llm=llm,
            chat_id=chat_id,
            existing_summary=existing_summary,
            focus_topic=focus_topic,
            progress_tracker=tracker,
            config=config,
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
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        for task in done:
            exc = task.exception()
            if exc is not None:
                raise exc
            if task is summarize_task:
                return task.result()

        raise RuntimeError("Unexpected: no task completed with result")
    except (InactivityTimeoutError, TotalCeilingTimeoutError) as timeout_exc:
        logger.warning(
            "⏱️ [compact_chat] Progress-aware timeout (%s) for chat %s — aborting compaction",
            timeout_exc,
            chat_id,
        )
        raise
    finally:
        for task in (summarize_task, watchdog_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(summarize_task, watchdog_task, return_exceptions=True)
