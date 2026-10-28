"""Harness async wakeup bridge — settles a finished background subagent into its chat and streams the wake turn.

[INPUT]
- app.services.agent.adaptive_wakeup::get_adaptive_wakeup_service (POS: routes a settlement, writes its notice row, queues the wake turn)
- app.services.agent.params::AgentRequest / convert_to_general_agent_params (POS: chat config → GeneralAgentParams)
- app.ai_agents::AgentFactory (POS: instantiate GeneralAgent for the wake turn)
- app.core.utils.chat_utils::convert_chat_history (POS: frontend-style chat tuples → LangChain messages)
- app.core.security.privacy_settings::privacy_agent_params (POS: persisted privacy switch → agent privacy params)
- app.services.agent.gateway::get_agent_gateway (POS: counts the run and reports the chat as generating / idle)
- app.services.agent.streaming_support.stream_collector::StreamContentCollector (POS: turns streamed events into the durable assistant message)
- app.services.chat.chat_service::ChatService (POS: chat business facade; loads the history, keeps the assistant reply)
- myrm_agent_harness.utils.runtime.cancellation::CancellationToken (POS: how a Stop, a goal pause and the emergency stop reach a turn)

[OUTPUT]
- ServerWakeupHandler.on_async_wakeup: hand a finished background subagent to the adaptive wakeup service
- ServerWakeupHandler.stream_wake_turn: build the agent and stream one wake turn the caller holds the chat for

[POS]
Business orchestration hook for Harness `ASYNC_WAKEUP`; runs per isolated server instance without Control Plane scheduling.
The wake turn streams to the chat through the app event bus. It runs under the caller's turn lease, so the chat's Stop
button, a goal pause and the emergency stop reach it like any other turn.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import aclosing
from typing import TYPE_CHECKING, cast

from myrm_agent_harness.agent.sub_agents.types import SubAgentResult
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

from app.core.security.privacy_settings import privacy_agent_params
from app.core.utils.chat_utils import convert_chat_history
from app.services.agent.streaming_support.stream_collector import StreamContentCollector
from app.services.chat.chat_service import ChatService

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage

    from app.ai_agents import GeneralAgent, GeneralAgentParams

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3
_tasks: set[asyncio.Task[None]] = set()


class ServerWakeupHandler:
    """Handles async wakeup events from the Harness framework in the background."""

    async def on_async_wakeup(self, result: SubAgentResult, agent_id: str, session_id: str | None) -> None:
        """Called by Harness when a background subagent (wait=False) completes.

        The settlement is routed in a detached task so the harness cleanup hook is not blocked.
        """
        if not session_id:
            logger.warning("Wakeup handler received event without session_id. Ignoring.")
            return

        logger.info("ServerWakeupHandler received wakeup for session %s, task %s", session_id, result.task_id)

        task = asyncio.create_task(self._process_wakeup(result, agent_id, session_id))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)

    async def _process_wakeup(self, result: SubAgentResult, agent_id: str, session_id: str) -> None:
        """Hand the settled subagent to the adaptive wakeup service in a detached background task."""
        try:
            from myrm_agent_harness.agent.coordination.adaptive_wakeup import (
                WakeupEvent,
                WakeupSourceType,
            )

            from app.services.agent.adaptive_wakeup import get_adaptive_wakeup_service

            status_str = "completed successfully" if result.success else "failed"
            event = WakeupEvent(
                source_type=WakeupSourceType.SUBAGENT,
                source_id=result.task_id,
                session_id=session_id,
                success=result.success,
                summary=f"Subagent '{result.agent_type}' {status_str}",
                duration_seconds=result.duration_seconds,
                error=result.error,
            )

            await get_adaptive_wakeup_service().handle_settlement(event, agent_id=agent_id)

        except Exception as e:
            logger.error(
                "Failed to process async wakeup for session %s: %s",
                session_id,
                e,
                exc_info=True,
            )

    async def stream_wake_turn(
        self,
        session_id: str,
        agent_id: str,
        turn_id: str,
        cancel_token: CancellationToken,
    ) -> None:
        """Build the agent and stream one wake turn.

        The caller holds ``session_id`` under ``server_turn_lease`` for ``turn_id``; ``cancel_token`` is the lease's
        token, which is what a Stop, a pause or the emergency stop flips.
        """
        from app.ai_agents import AgentFactory
        from app.core.channel_bridge.config_loader import load_user_configs
        from app.services.agent.execution_cache import ExecutionMode, finalize_agent_session
        from app.services.agent.params import AgentRequest, convert_to_general_agent_params
        from app.services.agent.runtime_context import build_agent_runtime_context
        from app.services.agent.session_credential_assembler import session_credentials_scope

        request = AgentRequest(
            message_id=turn_id,
            chat_id=session_id,
            query="[SYSTEM WAKEUP]",
            action_mode="general",
            agent_id=agent_id,
        )

        chat_history = await ChatService.load_web_chat_history(session_id, api_key=None)
        params = (await convert_to_general_agent_params(request, chat_history))[0]

        user_cfgs = await load_user_configs()
        wakeup_payload: dict[str, object] = {
            "channel_name": "headless_wakeup",
            **privacy_agent_params(user_cfgs.personal_settings_dict if user_cfgs else None),
        }
        if params.memory_channel_id is None:
            wakeup_payload["memory_channel_id"] = "web_chat"
        params = params.model_copy(update=wakeup_payload)

        runtime_context = await build_agent_runtime_context(execution_mode=ExecutionMode.POOLED)
        agent = AgentFactory.create_general_agent(params)

        async with session_credentials_scope(
            oauth_credentials_dict=(user_cfgs.oauth_credentials_dict if user_cfgs else None),
            providers_dict=user_cfgs.providers_dict if user_cfgs else None,
        ):
            try:
                await self._stream(session_id, agent, params, runtime_context, cancel_token)
            finally:
                await finalize_agent_session(
                    agent,
                    chat_id=params.chat_id,
                    agent_id=params.agent_id,
                    extra_context=runtime_context,
                )

    async def _stream(
        self,
        session_id: str,
        agent: GeneralAgent,
        params: GeneralAgentParams,
        runtime_context: dict[str, object],
        cancel_token: CancellationToken,
    ) -> None:
        """Relay the agent run to the chat, retrying a failed run, and keep what it said."""
        converted_history = await convert_chat_history(params.chat_history)
        collector = StreamContentCollector()
        try:
            for attempt in range(_MAX_ATTEMPTS):
                collector = StreamContentCollector()
                try:
                    await self._relay(session_id, agent, params, runtime_context, converted_history, cancel_token, collector)
                    logger.info("Headless wakeup agent run completed for session %s", session_id)
                    return
                except Exception as e:
                    logger.error("Headless wakeup stream error on attempt %d/%d: %s", attempt + 1, _MAX_ATTEMPTS, e)
                    if cancel_token.is_cancelled:
                        # A stopped turn is over; starting it again would undo the stop.
                        return
                    if attempt == _MAX_ATTEMPTS - 1:
                        logger.error(
                            "Headless wakeup failed permanently for session %s after %d attempts.",
                            session_id,
                            _MAX_ATTEMPTS,
                        )
                        return
                    await asyncio.sleep(2**attempt)
        finally:
            if collector.has_content:
                await ChatService.persist_assistant_message_safe(
                    session_id,
                    collector.content,
                    extra_data=collector.extra_data,
                    timezone=params.timezone,
                    request_message_id=params.message_id,
                )

    async def _relay(
        self,
        session_id: str,
        agent: GeneralAgent,
        params: GeneralAgentParams,
        runtime_context: dict[str, object],
        converted_history: list[BaseMessage],
        cancel_token: CancellationToken,
        collector: StreamContentCollector,
    ) -> None:
        """Run the agent once and publish each event; a stopped run ends with ``agent_cancelled`` like a chat turn."""
        from app.services.agent.gateway import get_agent_gateway

        raw_stream = agent.process_stream(
            query=cast(str | list[dict[str, object]], params.query),
            chat_history=converted_history,
            message_id=params.message_id,
            chat_id=params.chat_id,
            cancel_token=cancel_token,
            timezone=params.timezone,
            force_external_agent=params.force_external_agent,
            context=runtime_context,
        )
        stream = get_agent_gateway().execute_stream(
            raw_stream,
            agent_type="headless_wakeup",
            session_id=session_id,
            agent_instance=agent,
            active_message_id=params.message_id,
        )
        # Closing the stream on a stop hands the chat back at once instead of when the generator is collected.
        async with aclosing(stream):
            async for chunk in stream:
                if cancel_token.is_cancelled:
                    break
                self._publish(session_id, collector, chunk)

        if cancel_token.is_cancelled:
            logger.warning("Headless wakeup cancelled: message_id=%s, reason=%s", params.message_id, cancel_token.cancel_reason)
            self._publish(
                session_id,
                collector,
                {
                    "type": "agent_cancelled",
                    "messageId": params.message_id,
                    "data": {"reason": str(cancel_token.cancel_reason)},
                },
            )

    @staticmethod
    def _publish(session_id: str, collector: StreamContentCollector, payload: dict[str, object]) -> None:
        from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

        collector.feed_event(payload)
        get_event_bus().publish(
            AppEvent(
                event_type=AppEventType.ASYNC_AGENT_STREAM_CHUNK,
                data={"session_id": session_id, "chunk": payload},
            )
        )
