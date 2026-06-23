"""Main agent SSE stream loop."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, AsyncIterable
from dataclasses import dataclass

from myrm_agent_harness.utils.runtime.cancellation import CancelReason

from app.schemas.streaming import SSEEnvelope
from app.services.agent.stream_session.stream_lane_factory import (
    create_consensus_stream,
    create_deep_research_stream,
    create_fast_lane_stream,
)
from app.services.agent.stream_session.stream_session_types import AgentStreamSession
from app.services.agent.streaming import ai_agent_service_stream
from app.services.agent.streaming_support.sse_helpers import (
    extract_approval_intercepted,
    extract_approval_timeout,
    is_compression_exhausted,
)

logger = logging.getLogger(__name__)


@dataclass
class ApprovalTimeoutHolder:
    value: dict[str, object] | None = None


async def iter_agent_stream_chunks(
    session: AgentStreamSession,
    approval: ApprovalTimeoutHolder,
) -> AsyncGenerator[str, None]:
    stream: AsyncIterable[str | dict[str, object]]
    if session.request.action_mode == "deep_research":
        stream = create_deep_research_stream(session.params, session.cancel_token, session.research_model_cfg)
    elif session.request.action_mode == "consensus":
        stream = create_consensus_stream(
            session.params,
            session.cancel_token,
            consensus_cfg=session.consensus_config,
            reference_model_cfgs=session.consensus_ref_model_cfgs,
            aggregator_model_cfg=session.consensus_agg_model_cfg,
        )
    elif session.request.use_workflow:
        from app.services.agent.stream_session.stream_lane_factory import create_dynamic_workflow_stream

        logger.info(f"🚀 Dynamic Workflow Engine activated for message_id={session.params.message_id}")
        stream = create_dynamic_workflow_stream(session.params, session.cancel_token)
    elif (
        session.routing_tier == "simple"
        and session.request.blueprint_id is None
        and not session.request.mention_references
        and session.request.resume_value is None
        and session.request.action_mode == "fast"
        and not session.request.ephemeral_subagents
    ):
        logger.info(f"🚀 Fast Lane activated for message_id={session.params.message_id}")
        stream = create_fast_lane_stream(session.params, session.cancel_token)
    else:
        stream = ai_agent_service_stream(
            params=session.params,
            cancel_token=session.cancel_token,
            steering_token=session.steering_token,
            extra_context=session.extra_context,
        )

    estimated_tokens = 0
    last_reported_tokens = 0
    async for chunk in stream:
        if session.cancel_token.is_cancelled:
            logger.warning(
                "Agent cancelled: message_id=%s, reason=%s",
                session.params.message_id,
                session.cancel_token.cancel_reason,
            )
            # Cooperative cleanup: ``npm install`` / ``webpack --watch``
            # backgrounded by the agent must not outlive the cancelled
            # chat or they keep eating RAM/CPU/sandbox quota. Mirrors
            # ``hermes-agent`` ``process_registry.kill_all(task_id=...)``
            # called from its cleanup hook.
            if session.request.chat_id:
                try:
                    from myrm_agent_harness.agent.meta_tools.bash._background_registry import (
                        get_background_registry,
                    )

                    await get_background_registry().kill_session_jobs(session.request.chat_id)
                except Exception as exc:
                    logger.warning(
                        "Failed to kill background jobs for cancelled session %s: %s",
                        session.request.chat_id,
                        exc,
                    )
            cancel_event = {
                "type": "agent_cancelled",
                "messageId": session.params.message_id,
                "data": {"reason": str(session.cancel_token.cancel_reason)},
            }
            yield SSEEnvelope.from_any(cancel_event).to_sse_chunk()
            break

        if isinstance(chunk, dict) and chunk.get("type") == "message":
            text = chunk.get("data", "")
            if isinstance(text, str):
                estimated_tokens += len(text)

        if isinstance(chunk, dict) and chunk.get("type") == "token_usage":
            data_val = chunk.get("data", {})
            if isinstance(data_val, dict):
                usage = data_val.get("usage", {})
                if isinstance(usage, dict):
                    total = usage.get("total_tokens")
                    if isinstance(total, (int, float)):
                        total_tokens = int(total)
                        if total_tokens > estimated_tokens:
                            estimated_tokens = total_tokens

        if session.goal_provider and session.request.chat_id:
            if estimated_tokens - last_reported_tokens >= 20:
                last_reported_tokens = estimated_tokens
                active_goal = await session.goal_provider.get_active_goal(session.request.chat_id)
                if active_goal and active_goal.budget:
                    current_total = active_goal.tokens_used + estimated_tokens
                    max_tokens = active_goal.budget.max_tokens

                    from myrm_agent_harness.agent.goals.types import GoalStatus

                    if max_tokens is not None and current_total >= max_tokens and active_goal.status != GoalStatus.BUDGET_LIMITED:
                        logger.warning(
                            f"🎯 Real-time circuit breaker triggered! Estimated tokens: {current_total} >= {max_tokens}"
                        )
                        await session.goal_provider.update_status(active_goal.goal_id, GoalStatus.BUDGET_LIMITED)
                        active_goal.status = GoalStatus.BUDGET_LIMITED
                        session.cancel_token.cancel(CancelReason.USER_CANCELLED)  # Using USER_CANCELLED as a fallback

                    incremental_goal_status = {
                        "goal_id": active_goal.goal_id,
                        "objective": active_goal.objective,
                        "ui_summary": active_goal.ui_summary,
                        "status": active_goal.status.value,
                        "tokens_used": current_total,
                        "time_used_seconds": active_goal.time_used_seconds,
                        "turns_used": active_goal.turns_used,
                        "constraints": active_goal.constraints or [],
                        "budget": {
                            "max_tokens": active_goal.budget.max_tokens,
                            "max_usd": active_goal.budget.max_usd,
                            "max_time_seconds": active_goal.budget.max_time_seconds,
                            "max_turns": active_goal.budget.max_turns,
                        },
                    }

                    yield SSEEnvelope.from_any(
                        {
                            "type": "goal_status",
                            "messageId": session.params.message_id,
                            "data": incremental_goal_status,
                        }
                    ).to_sse_chunk()

                    if active_goal.status == GoalStatus.BUDGET_LIMITED:
                        warning_msg = "\n\n**预算已耗尽，任务自动暂停。**"
                        yield SSEEnvelope.from_any(
                            {
                                "type": "message",
                                "messageId": session.params.message_id,
                                "data": warning_msg,
                            }
                        ).to_sse_chunk()
                        session.collector.feed_sse(warning_msg)

                        try:
                            from app.services.infra.system_notification import (
                                SystemNotificationService,
                            )

                            await SystemNotificationService.create_notification(
                                title="Agent 预算已耗尽",
                                message=f"您的 Agent 会话由于达到 Token 预算上限（{active_goal.budget.max_tokens} Tokens）已自动暂停。请在聊天窗口中追加预算以恢复执行。",
                                type="warning",
                                source="goal_budget",
                                meta_data={
                                    "chat_id": session.request.chat_id,
                                    "goal_id": active_goal.goal_id,
                                },
                            )
                        except Exception as e:
                            logger.error(f"Failed to create system notification: {e}")

                        break

        if isinstance(chunk, str):
            sse_chunk = chunk if chunk.startswith("data: ") else f"data: {chunk}\n\n"
        else:
            try:
                # Forward rate_limit_warning directly
                if isinstance(chunk, dict) and chunk.get("type") == "rate_limit_warning":
                    chunk["messageId"] = session.params.message_id

                if isinstance(chunk, dict) and chunk.get("messageId") is None:
                    chunk["messageId"] = session.params.message_id

                # Inject goal_status into message_end and handle budget exhausted
                if isinstance(chunk, dict) and chunk.get("type") == "message_end":
                    # Inject memory citations and budget
                    try:
                        import re

                        content = session.collector.content
                        citations = list(set(re.findall(r"<cite:([^>]+)>", content)))
                        if citations:
                            chunk["citations"] = citations

                        from myrm_agent_harness.agent._skill_agent_context import get_memory_manager

                        manager = get_memory_manager()
                        if manager and hasattr(manager, "_last_budget"):
                            chunk["memoryBudget"] = manager._last_budget
                    except Exception as e:
                        logger.warning("Failed to inject memory insights into message_end: %s", e)

                    if session.request.chat_id:
                        from app.services.agent.goal_registry import (
                            GoalRegistry,
                        )

                        provider = GoalRegistry.get_provider(session.request.chat_id)
                        if provider:
                            latest = await provider.get_latest_goal(session.request.chat_id)
                            if latest:
                                chunk["goal_status"] = {
                                    "goal_id": latest.goal_id,
                                    "objective": latest.objective,
                                    "ui_summary": latest.ui_summary,
                                    "status": latest.status.value,
                                    "tokens_used": latest.tokens_used,
                                    "time_used_seconds": latest.time_used_seconds,
                                    "turns_used": latest.turns_used,
                                    "constraints": latest.constraints or [],
                                    "reason": latest.metadata.get("pause_reason"),
                                    "budget": (
                                        {
                                            "max_tokens": latest.budget.max_tokens,
                                            "max_usd": latest.budget.max_usd,
                                            "max_time_seconds": latest.budget.max_time_seconds,
                                            "max_turns": latest.budget.max_turns,
                                        }
                                        if latest.budget
                                        else None
                                    ),
                                }
                                if latest.status.value == "budget_limited":
                                    # 1. Yield a message chunk to the chat
                                    warning_msg = "\n\n**预算已耗尽，任务自动暂停。**"
                                    yield SSEEnvelope.from_any(
                                        {
                                            "type": "message",
                                            "messageId": session.params.message_id,
                                            "data": warning_msg,
                                        }
                                    ).to_sse_chunk()
                                    session.collector.feed_sse(warning_msg)

                                    # 2. Persist system notification
                                    try:
                                        from app.services.infra.system_notification import (
                                            SystemNotificationService,
                                        )

                                        await SystemNotificationService.create_notification(
                                            title="预算已耗尽",
                                            message="您的任务因预算耗尽已自动暂停，请点击追加预算以继续。",
                                            type="warning",
                                            source="goal_budget",
                                            meta_data={
                                                "chat_id": session.request.chat_id,
                                                "goal_id": latest.goal_id,
                                                "action_url": f"/{session.request.chat_id}",
                                            },
                                        )
                                    except Exception as e:
                                        logger.error(f"Failed to create budget limit notification: {e}")

                envelope = SSEEnvelope.from_any(chunk)
                sse_chunk = envelope.to_sse_chunk()
            except Exception as e:
                logger.error("SSEEnvelope serialization failed: %s", e, exc_info=True)
                sse_chunk = f"data: {str(chunk)}\n\n"

        session.collector.feed_sse(sse_chunk)
        updated = extract_approval_timeout(sse_chunk)
        if updated is not None:
            approval.value = updated

        intercepted_data = extract_approval_intercepted(sse_chunk)
        if intercepted_data and session.request.chat_id:
            decision = intercepted_data.decision
            if decision in ("approve", "reject", "approve_always", "feedback"):
                from app.services.chat.chat_service import ChatService

                try:
                    approval_processed_event = {
                        "type": "approval_processed",
                        "decision": decision,
                        "messageId": session.params.message_id,
                    }
                    yield SSEEnvelope.from_any(approval_processed_event).to_sse_chunk()
                except Exception as e:
                    logger.error(
                        f"Failed to process intercepted approval: {e}",
                        exc_info=True,
                    )

        if is_compression_exhausted(sse_chunk) and session.request.chat_id and session.request.resume_value is None:
            from app.platform_utils import get_session_factory
            from app.services.chat.chat_service import ChatService

            try:
                session_factory = get_session_factory()
                async with session_factory() as _db:
                    result = await ChatService.undo_last_turn(session.request.chat_id)
                    if result.success and result.deleted_count > 0:
                        logger.warning(
                            "🧹 Compression exhausted: removed %d message(s) from chat %s to prevent death loop",
                            result.deleted_count,
                            session.request.chat_id,
                        )
            except Exception as undo_err:
                logger.error(
                    "Failed to undo last turn after compression exhaustion: %s",
                    undo_err,
                )

            reset_event = {
                "type": "context_overflow_reset",
                "messageId": session.params.message_id,
                "data": {"chat_id": session.request.chat_id},
            }
            yield SSEEnvelope.from_any(reset_event).to_sse_chunk()

        yield sse_chunk
