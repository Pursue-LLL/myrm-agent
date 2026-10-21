"""Channel approval timeout scheduling and timeout notifications.

[INPUT]
- myrm_agent_harness.agent.middlewares.approval.scheduler::ApprovalTimeoutScheduler (POS: Approval timeout scheduling)
- myrm_agent_harness.agent.streaming.answer_draft::AnswerDraft (POS: Streamed answer text honouring the restart contract)
- executor_helpers.history (POS: Channel chat history persistence)
- app.core.agent.run_activity::track_background_agent_run (POS: marks the timeout auto-resume run in flight)

[OUTPUT]
- schedule_channel_approval_timeout, notify_channel_timeout_result

[POS]
Channel executor 辅助：审批超时自动 resume 与渠道通知。
"""

from __future__ import annotations

import logging

from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler
from myrm_agent_harness.agent.streaming.answer_draft import AnswerDraft
from myrm_agent_harness.utils.coercion import parse_float
from myrm_agent_harness.utils.text_utils import strip_internal_markers

from app.channels.types import OutboundMessage
from app.core.agent.run_activity import track_background_agent_run

from .history import (
    build_chat_history_with_metadata,
    load_history_without_persist,
    persist_assistant_message,
)

logger = logging.getLogger(__name__)


def _timeout_decision(resume_value: dict[str, object]) -> str:
    """Return ``approve`` or ``reject``: the decision the timeout scheduler applied."""
    return "approve" if resume_value.get("decision") == "approve" else "reject"


def schedule_channel_approval_timeout(
    channel: str,
    peer: str,
    chat_id: str,
    timeout_info: dict[str, object],
    params: object,
    *,
    user_id: str,
) -> None:
    """Register a backend timeout guard for a channel approval request."""
    timeout_seconds = parse_float(timeout_info.get("seconds", 300), 300.0)
    behavior = str(timeout_info.get("behavior", "deny"))
    scheduler_key = f"{channel}:{peer}"

    async def resume_after_timeout(resume_value: dict[str, object]) -> None:
        from langgraph.types import Command

        from app.ai_agents.agents import AgentFactory, GeneralAgentParams

        if not isinstance(params, GeneralAgentParams):
            logger.error("Channel timeout resume: unexpected params type: %s", type(params))
            return

        resume_params = params.model_copy()
        resume_params.query = Command(resume=resume_value)

        from app.services.agent.execution_cache import ExecutionMode, finalize_agent_session
        from app.services.agent.runtime_context import build_agent_runtime_context

        runtime_context = await build_agent_runtime_context(
            execution_mode=ExecutionMode.POOLED,
        )

        agent = AgentFactory.create_general_agent(resume_params)
        # The channel turn suspended its graph under this key; resuming under the chat id would open an empty thread.
        agent.approval_session_key = scheduler_key

        from app.services.agent.session_credential_assembler import user_config_session_credentials_scope

        async with user_config_session_credentials_scope(channel=channel):
            chat_history = build_chat_history_with_metadata(
                (await load_history_without_persist(f"{channel}:{peer}"))[1],
            )
            answer = AnswerDraft()
            next_timeout: dict[str, object] | None = None
            try:
                with track_background_agent_run():
                    async for event in agent.process_stream(
                        query=resume_params.query,
                        chat_history=chat_history or None,
                        chat_id=chat_id,
                        context=runtime_context,
                    ):
                        answer.feed(event)
                        if event.get("type", "") == "tool_approval_request":
                            data = event.get("data", {})
                            if isinstance(data, dict):
                                extensions = data.get("extensions", {})
                                timeout_ext = extensions.get("timeout", {}) if isinstance(extensions, dict) else {}
                                if isinstance(timeout_ext, dict):
                                    next_timeout = {
                                        "seconds": timeout_ext.get("seconds", 300),
                                        "behavior": timeout_ext.get("behavior", "deny"),
                                    }
            finally:
                await finalize_agent_session(
                    agent,
                    chat_id=chat_id,
                    agent_id=resume_params.agent_id,
                    extra_context=runtime_context,
                )

            content = strip_internal_markers(answer.text)
            if content.strip():
                await persist_assistant_message(chat_id, content)

            await notify_channel_timeout_result(
                channel,
                peer,
                _timeout_decision(resume_value),
                content.strip() or None,
                user_id=user_id,
            )

            if next_timeout:
                schedule_channel_approval_timeout(
                    channel=channel,
                    peer=peer,
                    chat_id=chat_id,
                    timeout_info=next_timeout,
                    params=resume_params,
                    user_id=user_id,
                )
            else:
                logger.info(
                    "Channel timeout auto-resume completed: key=%s, chat_id=%s",
                    scheduler_key,
                    chat_id,
                )

    async def resume_callback(resume_value: dict[str, object]) -> None:
        try:
            await resume_after_timeout(resume_value)
        except Exception:
            # The timer claimed the key before resuming; a run that died leaves the suspended graph unanswered,
            # so the claim goes back and the user's own reply is not refused as already resolved.
            ApprovalTimeoutScheduler.get().reopen(scheduler_key)
            raise

    ApprovalTimeoutScheduler.get().schedule(
        key=scheduler_key,
        timeout_seconds=timeout_seconds,
        behavior=behavior,
        resume_callback=resume_callback,
    )


async def notify_channel_timeout_result(
    channel: str,
    peer: str,
    decision: str,
    agent_response: str | None,
    *,
    user_id: str,
) -> None:
    """Send a notification to the channel after an approval timeout auto-resume."""
    from app.core.channel_bridge import channel_gateway

    action = "approved" if decision == "approve" else "denied"
    parts = [f"⏱ Approval timed out — auto-{action}."]
    if agent_response:
        parts.append(agent_response)
    content = "\n\n".join(parts)

    try:
        await channel_gateway.publish(
            OutboundMessage(
                channel=channel,
                recipient_id=peer,
                content=content,
                user_id=user_id,
            )
        )
    except Exception:
        logger.warning(
            "Failed to send timeout notification to channel=%s peer=%s",
            channel,
            peer,
        )
