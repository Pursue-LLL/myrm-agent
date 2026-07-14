"""ChannelAgentExecutor — bridge between IM channel inbound messages and the SkillAgent runtime.

[INPUT]
- myrm_agent_harness.agent (POS: Agent execution engine framework)
- app.channels.types (POS: Session identity, message types, reset policy definitions)
- app.core.channel_bridge.executor_helpers (POS: Stream accumulation, title generation)
- app.core.channel_bridge.agent_executor.execute_preamble (POS: Config/session/agent preamble.)
- app.core.channel_bridge.agent_executor.stream_events (POS: Harness stream event mapping for channel progress updates.)
- app.core.channel_bridge.agent_executor.execute_finalize (POS: Post-stream OutboundMessage assembly.)
- app.core.channel_bridge.agent_executor.execute_errors (POS: Channel error reply builders.)

[OUTPUT]
- ChannelAgentExecutor: async generator that processes an InboundMessage through
  config resolution → session management → Agent invocation → streaming response.

[POS]
Business-layer executor for IM/channel inbound messages. Bridges channel routing
to the SkillAgent runtime with session-aware context, auto-reset notification,
and streaming response assembly. Preamble, artifact deep links, and stream event
mapping live in sibling modules execute_preamble.py, artifact_deep_links.py,
and stream_events.py.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from uuid import uuid4

from myrm_agent_harness.api import ConfigIncompleteError
from myrm_agent_harness.api.hooks import set_approval_user_id
from myrm_agent_harness.toolkits.code_execution.interceptor import set_execution_interceptor
from myrm_agent_harness.toolkits.llms.errors import MyrmLLMError
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.ai_agents.agents import GeneralAgentParams
from app.channels.types import InboundMessage, OutboundMessage, ProgressUpdate, StreamingText, TopicContext
from app.core.channel_bridge.executor_helpers import StreamAccumulator, schedule_channel_approval_timeout
from app.services.agent.execution_cache import ExecutionMode, finalize_agent_session
from app.services.agent.fission_config import max_parallel_from_engine_params
from app.services.agent.swarm_fission_resume import stream_with_swarm_fission_resume
from app.services.checkpoint.snapshot_service import SnapshotInterceptor

from .execute_errors import (
    build_config_incomplete_reply,
    build_generic_error_reply,
    build_llm_error_reply,
)
from .execute_finalize import finalize_channel_stream_reply
from .execute_preamble import prepare_channel_execution
from .stream_events import ChannelStreamEventState, iter_channel_stream_progress

logger = logging.getLogger(__name__)

set_execution_interceptor(SnapshotInterceptor())


class ChannelAgentExecutor:
    """Executes Agent tasks for inbound channel messages.

    Reads all user configs from the UserConfig table (same configs the
    frontend stores) to ensure channel messages have full Agent capabilities:
    model, filter model, search, MCP, retrieval, memory, and user instructions.
    """

    async def execute_stream(
        self,
        msg: InboundMessage,
        user_id: str = "",
        *,
        cancel_token: CancellationToken | None = None,
        steering_token: SteeringToken | None = None,
        topic_context: TopicContext | None = None,
    ) -> AsyncGenerator[ProgressUpdate | StreamingText | OutboundMessage, None]:
        agent = None
        token_ctx = None
        chat_id = ""
        params: GeneralAgentParams | None = None
        is_resume = bool(msg.resume_value)
        stream_state = ChannelStreamEventState()

        # Bind the resolved user_id into the harness approval ContextVar so the
        # downstream allow-always path (`add_to_allowlist_if_needed`) keys the
        # allowlist entry on the real user instead of `DEFAULT_USER_ID`.
        # This is the single integration point where channel-resolved identity
        # crosses into the harness approval subsystem.
        set_approval_user_id(user_id or msg.user_id or msg.sender_id)

        try:
            prep_result = await prepare_channel_execution(
                self,
                msg,
                is_resume=is_resume,
                topic_context=topic_context,
            )
            for pre_event in prep_result.pre_events:
                yield pre_event
            if prep_result.prep is None:
                return

            prep = prep_result.prep
            agent = prep.agent
            token_ctx = prep.token_ctx
            chat_id = prep.chat_id
            chat_history = prep.chat_history
            query_input = prep.query_input
            channel_budget_key = prep.channel_budget_key
            memory_settings = prep.memory_settings
            lite_model_cfg = prep.lite_model_cfg
            session_was_auto_reset = prep.session_was_auto_reset
            session_policy = prep.session_policy
            params = prep.params
            agent_engine_params = prep.agent_engine_params
            user_timezone = prep.user_timezone

            acc = StreamAccumulator()
            assistant_message_id = str(uuid4())

            async def _open_channel_stream(
                q: object,
            ) -> AsyncGenerator[dict[str, object], None]:
                async for event in agent.process_stream(
                    query=q,
                    chat_history=chat_history or None,
                    message_id=assistant_message_id,
                    chat_id=chat_id,
                    cancel_token=cancel_token,
                    steering_token=steering_token,
                    timezone=user_timezone,
                    context={"execution_mode": ExecutionMode.POOLED},
                ):
                    if isinstance(event, dict):
                        yield event

            async for progress in iter_channel_stream_progress(
                stream_with_swarm_fission_resume(
                    agent,
                    query_input,
                    _open_channel_stream,
                    max_concurrent=max_parallel_from_engine_params(agent_engine_params),
                ),
                acc,
                stream_state,
            ):
                yield progress

            reply, tmp_paths = await finalize_channel_stream_reply(
                msg,
                acc=acc,
                chat_id=chat_id,
                message_id=assistant_message_id,
                channel_budget_key=channel_budget_key,
                memory_settings=memory_settings,
                lite_model_cfg=lite_model_cfg,
                chat_history=chat_history,
                session_was_auto_reset=session_was_auto_reset,
                session_policy=session_policy,
            )
            try:
                yield reply
            finally:
                for p in tmp_paths:
                    try:
                        os.unlink(p)
                    except OSError:
                        pass
        except ConfigIncompleteError as exc:
            logger.warning(
                "ChannelAgentExecutor: config incomplete for %s: %s",
                msg.sender_id,
                exc.technical_details,
            )
            yield build_config_incomplete_reply(msg, exc)
        except MyrmLLMError as exc:
            logger.error("ChannelAgentExecutor: agent failed for %s: %s", msg.sender_id, exc)
            yield build_llm_error_reply(msg, exc)
        except Exception as exc:
            logger.error(
                "ChannelAgentExecutor: agent failed for %s: %s",
                msg.sender_id,
                exc,
                exc_info=True,
            )
            yield build_generic_error_reply(msg, exc)
        finally:
            if token_ctx is not None:
                from myrm_agent_harness.agent.security import user_credentials_ctx

                user_credentials_ctx.reset(token_ctx)
            if stream_state.approval_timeout_info and chat_id and params is not None:
                schedule_channel_approval_timeout(
                    channel=msg.channel,
                    peer=msg.chat_id or msg.sender_id,
                    chat_id=chat_id,
                    timeout_info=stream_state.approval_timeout_info,
                    params=params,
                    user_id=msg.user_id or msg.sender_id or "",
                )
            if agent and params is not None:
                await finalize_agent_session(
                    agent,
                    chat_id=chat_id,
                    agent_id=params.agent_id,
                    extra_context={"execution_mode": ExecutionMode.POOLED},
                )
