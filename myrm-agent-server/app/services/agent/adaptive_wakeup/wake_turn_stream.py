"""Run one wake turn of a chat: build its agent, relay the run to the chat and keep what it said.

[INPUT]
- app.services.chat.chat_service::ChatService (POS: the chat row (its agent and incognito flag), the history, the durable assistant reply)
- app.services.agent.params::AgentRequest / convert_to_general_agent_params (POS: chat config -> GeneralAgentParams)
- app.ai_agents::AgentFactory (POS: instantiate the chat's GeneralAgent)
- app.core.utils.chat_utils::convert_chat_history (POS: frontend-style chat tuples -> LangChain messages)
- app.core.security.privacy_settings::privacy_agent_params (POS: persisted privacy switch -> agent privacy params)
- app.services.agent.gateway::get_agent_gateway (POS: counts the run and reports the chat as generating / idle)
- app.services.agent.streaming_support.stream_collector::StreamContentCollector (POS: turns streamed events into the durable assistant message)
- app.services.event.app_event_bus::get_event_bus (POS: carries the streamed chunks to the open chat)
- myrm_agent_harness.utils.runtime.cancellation::CancellationToken (POS: how a Stop, a goal pause and the emergency stop reach a turn)

[OUTPUT]
- WAKE_TURN_FAILED_ERROR_KIND: the ``error_kind`` of the stream event that tells the chat a wake turn failed for good
- stream_wake_turn: build the agent of a chat, stream one wake turn the caller holds the chat for, and return what the
  turn said when it finished normally (``None`` after a Stop, a failure or an empty answer)

[POS]
The streaming half of a wake turn. The turn belongs to the chat's own agent, streams to the chat through the app event
bus, and runs under the caller's turn lease, so the chat's Stop button, a goal pause and the emergency stop reach it
like any other turn. It runs incognito exactly when its chat is, so a private chat's follow-up leaves no memory either.
A run is retried only while it has shown the user nothing; a run that fails for good leaves an
error event in the chat and on its saved reply instead of silence. The reply is saved before it is returned, so
whoever carries it outside the app finds it in the chat's history too.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import aclosing
from typing import TYPE_CHECKING

from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

from app.core.security.privacy_settings import privacy_agent_params
from app.core.utils.chat_utils import convert_chat_history
from app.services.agent.streaming_support.stream_collector import StreamContentCollector
from app.services.chat.chat_service import ChatService

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage

    from app.ai_agents import GeneralAgent, GeneralAgentParams

logger = logging.getLogger(__name__)

WAKE_TURN_FAILED_ERROR_KIND = "wake_turn_failed"

_MAX_ATTEMPTS = 3

# How a run that did not finish its answer ends (as ``completionStatus`` and as the category of its stop reason);
# what such a run said is not an answer to hand to anyone.
_UNFINISHED_ENDINGS = frozenset({"cancelled", "error"})


async def stream_wake_turn(chat_id: str, turn_id: str, cancel_token: CancellationToken) -> str | None:
    """Build the agent of ``chat_id`` and stream one wake turn; return its reply when the run finished normally.

    The caller holds ``chat_id`` under ``server_turn_lease`` for ``turn_id``; ``cancel_token`` is the lease's token,
    which is what a Stop, a pause or the emergency stop flips.
    """
    from app.ai_agents import AgentFactory
    from app.core.channel_bridge.config_loader import load_user_configs
    from app.services.agent.execution_cache import ExecutionMode, finalize_agent_session
    from app.services.agent.params import AgentRequest, convert_to_general_agent_params
    from app.services.agent.runtime_context import build_agent_runtime_context
    from app.services.agent.session_credential_assembler import session_credentials_scope

    chat = await ChatService.get_chat_metadata(chat_id)
    if chat is None:
        logger.warning("Wake turn not run, the chat no longer exists: session=%s", chat_id)
        return None

    request = AgentRequest(
        message_id=turn_id,
        chat_id=chat_id,
        query="[SYSTEM WAKEUP]",
        action_mode="general",
        agent_id=chat.agent_id,
        # The incognito flag lives on the chat row, so the follow-up turn keeps the promise the chat's own turns keep.
        incognito_mode=chat.is_incognito,
    )

    chat_history = await ChatService.load_web_chat_history(chat_id, api_key=None)
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
            return await _stream_with_retries(chat_id, agent, params, runtime_context, cancel_token)
        finally:
            await finalize_agent_session(
                agent,
                chat_id=params.chat_id,
                agent_id=params.agent_id,
                extra_context=runtime_context,
            )


async def _stream_with_retries(
    chat_id: str,
    agent: GeneralAgent,
    params: GeneralAgentParams,
    runtime_context: dict[str, object],
    cancel_token: CancellationToken,
) -> str | None:
    """Relay the agent run to the chat, retry a run that failed before saying anything, and keep what it said.

    Returns the reply of a run that finished normally; a stopped or failed run returns ``None``.
    """
    converted_history = await convert_chat_history(params.chat_history)
    collector = StreamContentCollector()
    try:
        for attempt in range(_MAX_ATTEMPTS):
            collector = StreamContentCollector()
            try:
                await _relay(chat_id, agent, params, runtime_context, converted_history, cancel_token, collector)
                logger.info("Headless wakeup agent run completed for session %s", chat_id)
                return _finished_reply(collector, cancel_token)
            except Exception as e:
                logger.error("Headless wakeup stream error on attempt %d/%d: %s", attempt + 1, _MAX_ATTEMPTS, e)
                if cancel_token.is_cancelled:
                    # A stopped turn is over; starting it again would undo the stop.
                    return None
                # What the run already streamed stays in the chat, so starting over would show it twice.
                if collector.has_active_generation or attempt == _MAX_ATTEMPTS - 1:
                    logger.error("Headless wakeup failed permanently for session %s after %d attempt(s).", chat_id, attempt + 1)
                    _publish(
                        chat_id,
                        collector,
                        {
                            "type": "error",
                            "error": "The autonomous follow-up could not be completed.",
                            "error_kind": WAKE_TURN_FAILED_ERROR_KIND,
                            "messageId": params.message_id,
                        },
                    )
                    collector.mark_stream_completion_error()
                    return None
                await asyncio.sleep(2**attempt)
        return None
    finally:
        if collector.has_persistable_turn:
            await ChatService.persist_assistant_message_safe(
                chat_id,
                collector.content,
                extra_data=collector.extra_data,
                timezone=params.timezone,
                request_message_id=params.message_id,
            )


def _finished_reply(collector: StreamContentCollector, cancel_token: CancellationToken) -> str | None:
    """What the run said, when it ended on its own with an answer; ``None`` after a Stop, an error or an empty answer."""
    if cancel_token.is_cancelled:
        return None
    extra_data = collector.extra_data or {}
    if extra_data.get("completionStatus") in _UNFINISHED_ENDINGS:
        return None
    stop_reason = extra_data.get("stopReason")
    if isinstance(stop_reason, dict) and stop_reason.get("category") in _UNFINISHED_ENDINGS:
        return None
    return collector.content.strip() or None


async def _relay(
    chat_id: str,
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
        query=params.query,
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
        session_id=chat_id,
        agent_instance=agent,
        active_message_id=params.message_id,
    )
    # Closing the stream on a stop hands the chat back at once instead of when the generator is collected.
    async with aclosing(stream):
        async for chunk in stream:
            if cancel_token.is_cancelled:
                break
            _publish(chat_id, collector, chunk)

    if cancel_token.is_cancelled:
        logger.warning("Headless wakeup cancelled: message_id=%s, reason=%s", params.message_id, cancel_token.cancel_reason)
        _publish(
            chat_id,
            collector,
            {
                "type": "agent_cancelled",
                "messageId": params.message_id,
                "data": {"reason": str(cancel_token.cancel_reason)},
            },
        )


def _publish(chat_id: str, collector: StreamContentCollector, payload: dict[str, object]) -> None:
    from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

    collector.feed_event(payload)
    get_event_bus().publish(
        AppEvent(
            event_type=AppEventType.ASYNC_AGENT_STREAM_CHUNK,
            data={"session_id": chat_id, "chunk": payload},
        )
    )
