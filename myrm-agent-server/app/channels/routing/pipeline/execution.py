"""Agent execution: resolve the topic, prepare the context, run the turn.

[INPUT]
- channels.routing.pipeline.delivery::RouterDeliveryMixin (POS: typing/placeholder effects, reply delivery, draft hold, cleanup)
- channels.routing.pipeline.hosts::RouterExecutionHost (POS: typing protocol for the router attributes this mixin uses)
- channels.routing.context_document::enrich_context_document (POS: document-text enrichment right before the executor stream)
- channels.routing.pending_approvals::resume_topic_context (POS: the topic context a resumed approval run is given)
- channels.routing.router_models::_ActiveTask, _AgentTurnScratch, _RouterExecutionContext (POS: internal data classes)
- channels.routing.session_gate::gate_key (POS: the session key of a message in the SessionGate, recorded on the running task for the watchdog's release)

[OUTPUT]
- RouterExecutionMixin: ``_resolve_topic``, ``_prepare_execution_context`` and ``_execute_prepared_context``, and
  ``deliver_followup`` (the one way to say something in a conversation that no message just asked for)

[POS]
Execution segment of ``AgentRouter``, composed into it via multiple inheritance. It builds on ``RouterDeliveryMixin``
and runs after ``RouterTurnMixin`` (``pipeline/turn.py``) has handed it one merged message.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import time

from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.channels.i18n import get_text, resolve_message_locale
from app.channels.routing.context_document import enrich_context_document
from app.channels.routing.pending_approvals import METADATA_APPROVAL_TIMED_OUT_KEY, resume_topic_context
from app.channels.routing.pipeline.delivery import RouterDeliveryMixin
from app.channels.routing.pipeline.hosts import RouterExecutionHost
from app.channels.routing.placeholder_strategy import (
    DeferredPlaceholder,
)
from app.channels.routing.router_keys import routing_state_key
from app.channels.routing.router_models import (
    _ActiveTask,
    _AgentTurnScratch,
    _RouterExecutionContext,
)
from app.channels.routing.session_gate import gate_key
from app.channels.types import (
    InboundMessage,
    TopicContext,
)
from app.channels.types.topics import METADATA_ROUTE_AGENT_KEY

logger = logging.getLogger("app.channels.routing.router")


class RouterExecutionMixin(RouterDeliveryMixin):
    """Mixin: execution lifecycle — prepare the context and run the turn; effects and delivery come from ``RouterDeliveryMixin``."""

    async def _resolve_topic(self: RouterExecutionHost, msg: InboundMessage) -> TopicContext | None:
        """Load per-thread or per-channel overrides when a TopicManager is configured.
        Also syncs topic metadata for auto-discovery in the UI.
        """
        if self._topic_resolver is None:
            return None
        chat_id = msg.chat_id or msg.sender_id

        # Sync metadata for auto-discovery
        chat_name = msg.metadata.get("chat_name") if msg.metadata else None
        chat_avatar_url = msg.metadata.get("chat_avatar_url") if msg.metadata else None

        if isinstance(chat_name, str) or isinstance(chat_avatar_url, str):
            # Try to sync, but catch exceptions to avoid failing message processing
            try:
                await self._topic_resolver.sync_topic_metadata(
                    msg.channel,
                    chat_id,
                    msg.thread_id,
                    display_name=chat_name if isinstance(chat_name, str) else None,
                    avatar_url=(chat_avatar_url if isinstance(chat_avatar_url, str) else None),
                )
            except Exception as e:
                logger.warning("Failed to sync topic metadata: %s", e)

        # 1. Thread-level binding
        if msg.thread_id:
            ctx = await self._topic_resolver.resolve_topic(msg.channel, chat_id, msg.thread_id)
            if ctx is not None:
                return dataclasses.replace(ctx, matched_by="thread_binding")

        # 2. Chat-level binding (Group/DM)
        ctx = await self._topic_resolver.resolve_topic(msg.channel, chat_id, None)
        if ctx is not None:
            return dataclasses.replace(ctx, matched_by="chat_binding")

        # 3. Channel-level global binding
        ctx = await self._topic_resolver.resolve_topic(msg.channel, "__global__", None)
        if ctx is not None:
            return dataclasses.replace(ctx, matched_by="channel_binding")

        return None

    async def deliver_followup(self: RouterExecutionHost, origin: InboundMessage, content: str) -> bool:
        """Say ``content`` in the conversation ``origin`` came from, though no message just asked for it.

        The reply goes out like the answer to a message: the silent-reply filter, the web hand-off button and draft
        review all apply (a topic that holds replies for review gets a draft, and the reply is withheld when it cannot
        be held), and a topic that has been disabled since gets nothing.

        Returns True when the reply was sent to the channel.
        """
        chat_id = origin.chat_id or origin.sender_id
        topic_ctx = await self._resolve_topic(origin)
        if topic_ctx is not None and not topic_ctx.enabled:
            logger.warning(
                "AgentRouter: topic %s disabled in %s/%s, follow-up not sent", origin.thread_id, origin.channel, chat_id
            )
            return False
        reply = dataclasses.replace(origin.get_or_create_correlation_context().create_reply(content), recipient_id=chat_id)
        return await self._deliver_agent_result(reply, None, origin, chat_id, 0.0, False, topic_ctx=topic_ctx)

    async def _prepare_execution_context(self: RouterExecutionHost, inbound: InboundMessage) -> _RouterExecutionContext | None:
        """Prepare execution context: identity resolution, session check, topic validation.

        Returns:
            Frozen context or None to skip processing.
            ``exec_msg`` is the inbound message after group-policy transforms (prefix strip, context buffer).
        """
        chat_id = inbound.chat_id or inbound.sender_id
        state_key = routing_state_key(inbound.channel, chat_id, inbound.thread_id)

        if inbound.resume_value and inbound.metadata.get(METADATA_APPROVAL_TIMED_OUT_KEY) and inbound.user_id:
            # The router built this message itself to resume a run for the sender it already admitted: no new admission.
            user_id, exec_msg = inbound.user_id, inbound
        elif inbound.is_group:
            resolved = await self._resolver.resolve_group_user(inbound)
            if not resolved:
                return None
            user_id, exec_msg = resolved
        else:
            dm_user = await self._resolver.resolve_dm_user(inbound)
            if dm_user is None:
                return None
            user_id = dm_user
            exec_msg = inbound

        message_id = exec_msg.message_id
        if message_id is None:
            raw_mid = exec_msg.metadata.get("message_id")
            message_id = raw_mid if isinstance(raw_mid, str) else None

        if state_key in self._new_session_peers:
            del self._new_session_peers[state_key]
            exec_msg.metadata["force_new_epoch"] = True

        topic_ctx = await self._resolve_topic(exec_msg)
        if topic_ctx and not topic_ctx.enabled:
            logger.warning(
                "AgentRouter: topic %s disabled in %s/%s, skipping",
                exec_msg.thread_id,
                exec_msg.channel,
                chat_id,
            )
            return None

        route_agent_id = exec_msg.metadata.get(METADATA_ROUTE_AGENT_KEY)
        if isinstance(route_agent_id, str):
            from app.core.channel_bridge.topic_config import SqlTopicManager
            from app.services.agent.agent_service import AgentService

            route_agent = await AgentService.get_agent_by_id(route_agent_id)
            if route_agent is not None and SqlTopicManager._agent_is_search_track(route_agent):
                logger.warning(
                    "AgentRouter: reject search-track route_agent_id %s on channel %s",
                    route_agent_id,
                    exec_msg.channel,
                )
            else:
                topic_ctx = TopicContext(
                    topic_id=exec_msg.thread_id or chat_id,
                    agent_id=route_agent_id,
                    enabled=True,
                    matched_by="alias",
                )
                logger.warning("AgentRouter: routing to agent %s via subcommand", route_agent_id)

        if topic_ctx and topic_ctx.personality_style:
            exec_msg.metadata["personality_style"] = topic_ctx.personality_style

        return _RouterExecutionContext(
            user_id=user_id,
            state_key=state_key,
            chat_id=chat_id,
            message_id=message_id,
            topic_ctx=topic_ctx,
            exec_msg=exec_msg,
        )

    async def _execute_prepared_context(
        self: RouterExecutionHost,
        ctx: _RouterExecutionContext,
        scratch: _AgentTurnScratch,
        *,
        is_resume: bool,
        inbound_had_voice: bool,
    ) -> None:
        """Register active task, run side effects, stream agent, deliver result, cleanup.

        Updates ``scratch.placeholder_id`` for the enclosing handler's error path.
        """
        cancel_token = CancellationToken(request_id=str(ctx.message_id or ""))
        steering_token = SteeringToken()
        current_task = asyncio.current_task()
        assert current_task is not None
        session_gate_key = gate_key(ctx.exec_msg)
        self._active_tasks[ctx.state_key] = _ActiveTask(
            task=current_task,
            cancel_token=cancel_token,
            channel=ctx.exec_msg.channel,
            chat_id=ctx.chat_id,
            placeholder_id=None,
            started_at=time.monotonic(),
            requester_id=ctx.exec_msg.sender_id or "",
            locale=resolve_message_locale(ctx.exec_msg),
            steering_token=steering_token,
            gate_key=session_gate_key,
            gate_turn=self._gate.running_turn(session_gate_key),
        )

        scratch.deferred_placeholder = await self._setup_message_effects(
            ctx.exec_msg,
            ctx.state_key,
            ctx.chat_id,
            ctx.message_id,
            is_resume,
        )

        try:
            # Read now, not on arrival: the journal and the data-plane ledger snapshot the message before this point.
            stream_msg = ctx.exec_msg if is_resume else await enrich_context_document(ctx.exec_msg, self._bus.get_channel)
            result, last_progress_at = await self._consume_executor_stream(
                stream_msg,
                ctx.user_id,
                ctx.state_key,
                ctx.chat_id,
                cancel_token=cancel_token,
                steering_token=steering_token,
                # A resumed run keeps the session of the turn that asked, whose key carries the agent.
                topic_context=resume_topic_context(ctx.topic_ctx, ctx.exec_msg) if is_resume else ctx.topic_ctx,
                # Independent of ``is_resume``: a resumed turn streams the same held reply.
                hold_reply=ctx.topic_ctx is not None and ctx.topic_ctx.holds_reply_for_review,
            )
            deferred = scratch.deferred_placeholder if isinstance(scratch.deferred_placeholder, DeferredPlaceholder) else None
            delivered = await self._deliver_agent_result(
                result,
                deferred,
                ctx.exec_msg,
                ctx.chat_id,
                last_progress_at,
                inbound_had_voice,
                topic_ctx=ctx.topic_ctx,
            )
            scratch.completed = True
            if ctx.exec_msg.is_group:
                from app.channels.routing.follow_up import (
                    maybe_post_completion_receipt,
                    note_group_activity,
                )

                note_group_activity(
                    ctx.exec_msg.channel,
                    ctx.chat_id,
                    ctx.exec_msg.thread_id,
                    ctx.exec_msg.sender_id,
                    ctx.exec_msg.sender_name,
                    resolve_message_locale(ctx.exec_msg),
                )
                active = self._active_tasks.get(ctx.state_key)
                elapsed = time.monotonic() - active.started_at if active is not None else 0.0
                from app.channels.routing.channel_data_plane import ChannelDataPlaneService

                await maybe_post_completion_receipt(
                    bus=self._bus,
                    topic=ctx.topic_ctx,
                    msg=ctx.exec_msg,
                    chat_id=ctx.chat_id,
                    elapsed_seconds=elapsed,
                    is_resume=is_resume,
                    delivered=delivered,
                    record_outbound=ChannelDataPlaneService.record_outbound,
                )
        except asyncio.CancelledError:
            logger.warning(
                "AgentRouter: task cancelled for %s/%s",
                ctx.exec_msg.channel,
                ctx.chat_id,
            )
        except Exception as inner_exc:
            logger.warning(
                "AgentRouter: agent execution failed for %s/%s: %s",
                ctx.exec_msg.channel,
                ctx.exec_msg.sender_id,
                inner_exc,
            )
            if isinstance(scratch.deferred_placeholder, DeferredPlaceholder):
                resolved_id = await scratch.deferred_placeholder.resolve_for_delivery(None)
                if resolved_id:
                    await self._fx.cleanup_placeholder(
                        ctx.exec_msg.channel,
                        ctx.chat_id,
                        resolved_id,
                        get_text(
                            ctx.exec_msg,
                            "placeholder_execution_error",
                            error="execution error",
                        ),
                    )
                scratch.deferred_placeholder = None
            raise
        finally:
            placeholder_id = self._resolve_live_placeholder_id(ctx.state_key)
            await self._cleanup_effects(
                ctx.state_key,
                ctx.chat_id,
                ctx.exec_msg.channel,
                placeholder_id,
            )
