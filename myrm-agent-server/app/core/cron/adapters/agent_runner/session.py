"""Cron Agent 的重试策略与会话后置动作。

[POS]
agent_runner 的会话级辅助：重试退避、心跳情境报告注入、活跃目标入队。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.cron.situation import (
    SituationContext,
    SituationReportBuilder,
)
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    JobResult,
    ScheduleKind,
)

from . import support
from .support import _OVERLOAD_RETRY_DELAY, _build_effective_prompt

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


async def run_with_retries(
    job: CronJob, *, context: str, run_once: Callable[..., Awaitable[JobResult]]
) -> JobResult:
    overload_reason = support._memory_overload_reason()
    if overload_reason is not None:
        # Skip now, retry next tick: skipped runs don't consume retries or
        # increment failure counters (JobResult.skipped contract).
        logger.warning(
            "Cron agent job %s deferred: %s. Retrying on next tick.",
            job.id,
            overload_reason,
        )
        # A one-shot job has no next slot: without a retry time the skip would consume it.
        retry_at = datetime.now(timezone.utc) + _OVERLOAD_RETRY_DELAY if job.schedule.kind is ScheduleKind.ONCE else None
        return JobResult(success=False, skipped=True, skip_reason=overload_reason, retry_at=retry_at)
    last_result = JobResult(success=False, error="never executed")

    for attempt in range(1 + job.max_retries):
        last_result = await run_once(job, context=context)
        if last_result.success or last_result.skipped or last_result.retry_at is not None:
            # A skip waits for the next regular slot and a deferral names the instant a repeat can succeed;
            # retrying now only burns attempts.
            return last_result

        # If circuit breaker was tripped, abort immediately — do not retry!
        if getattr(last_result, "circuit_broken", False):
            logger.error(
                "Cron agent job %s circuit broken (attempt %d/%d): %s. Aborting retries to protect resources.",
                job.id,
                attempt + 1,
                1 + job.max_retries,
                last_result.error,
            )
            return last_result

        # A run whose steps may already have taken effect (a send, a write, a payment), that spent its whole time
        # budget, or whose failure no repeat can clear would only do it all again.
        if not last_result.retry_safe:
            logger.warning(
                "Cron agent job %s failed and is not safe to repeat (attempt %d/%d): %s. Not retrying in-process.",
                job.id,
                attempt + 1,
                1 + job.max_retries,
                last_result.error,
            )
            return last_result

        if attempt < job.max_retries:
            backoff = min(job.retry_backoff_ms * (2**attempt), 30_000)
            jitter = int(datetime.now(timezone.utc).microsecond % 250)
            await asyncio.sleep((backoff + jitter) / 1000)

    return last_result

async def inject_situation_report(job: CronJob, prompt: str, builder: SituationReportBuilder | None) -> tuple[str, bool]:
    """Build and prepend a situation report for heartbeat jobs.

    Returns ``(effective_prompt, has_actionable_content)`` so the caller
    can skip the LLM call when no section produced useful data.
    """
    assert builder is not None
    from app.core.channel_bridge.config_loader import load_user_configs
    from app.core.memory.proactive.delivery_tracker import (
        begin_follow_up_delivery,
        reset_follow_up_delivery,
    )
    from app.core.memory.proactive.settings import resolve_memory_enabled

    begin_follow_up_delivery()
    try:
        user_cfgs = await load_user_configs()
        memory_settings = user_cfgs.personal_settings_dict or {}
        memory_enabled = resolve_memory_enabled(memory_settings)

        ctx = SituationContext(
            last_tick_at=job.last_run_at,
            agent_id=job.agent_id or "",
            user_id=job.user_id,
            memory_enabled=memory_enabled,
        )
        report = await builder.build(ctx)
        if report:
            return (
                f"<situation_report>\n{report}</situation_report>\n\n{prompt}",
                True,
            )
    except Exception:
        logger.warning("Situation report build failed for job %s", job.id, exc_info=True)
        reset_follow_up_delivery()
        return prompt, True
    reset_follow_up_delivery()
    return prompt, False

async def try_enqueue_if_goal_active(job: CronJob, *, context: str = "") -> bool:
    """If an active goal exists on this chat, enqueue the cron task as a queued goal.

    Returns True if the job was enqueued (caller should skip direct execution).
    """
    from app.services.agent.goals.goal_registry import GoalRegistry

    chat_id = job.chat_id
    if not chat_id:
        return False

    provider = GoalRegistry.get_provider(chat_id)
    if not provider:
        return False

    active = await provider.get_active_goal(chat_id)
    if not active:
        return False

    effective_prompt = _build_effective_prompt(job)
    if context:
        effective_prompt = f"{effective_prompt}\n\n{context}"

    objective = f"[Cron: {job.name}] {effective_prompt[:200]}"
    criteria = list(job.acceptance_criteria) if job.acceptance_criteria else None
    await provider.create_goal(
        session_id=chat_id,
        objective=objective,
        acceptance_criteria=criteria,
    )
    logger.info(
        "Cron job %s enqueued as goal on chat %s (active goal: %s, criteria=%d)",
        job.id,
        chat_id,
        active.goal_id,
        len(criteria) if criteria else 0,
    )
    return True
