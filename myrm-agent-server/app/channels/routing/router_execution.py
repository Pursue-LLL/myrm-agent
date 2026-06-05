"""Agent execution lifecycle: prepare context, run effects, stream, deliver, cleanup.

[POS]
`RouterExecutionMixin` is composed into `AgentRouter` via multiple inheritance;
methods use `RouterExecutionHost` to constrain `self` attributes.
containslevelbyfallback(Thread -> Chat -> Channel)andmetadataautomaticallydiscovers(sync_topic_metadata)logic.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import time

from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.channels.i18n import channel_t, get_text
from app.channels.routing.placeholder_strategy import (
    DeferredPlaceholder,
)
from app.channels.routing.router_constants import (
    _MIN_PROGRESS_INTERVAL,
)
from app.channels.routing.router_host import RouterExecutionHost
from app.channels.routing.router_keys import routing_session_key
from app.channels.routing.router_models import (
    _ActiveTask,
    _AgentTurnScratch,
    _CleanupEntry,
    _RouterExecutionContext,
)
from app.channels.types import (
    InboundMessage,
    OutboundMessage,
    ReactionLevel,
    TopicContext,
)
from app.channels.types.notification import with_final_notify
from app.channels.voice.handler import maybe_tts

logger = logging.getLogger("app.channels.routing.router")


class RouterExecutionMixin:
    """Mixin: execution lifecycle — prepare, effects, stream, deliver, cleanup."""

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
                import logging

                logging.getLogger(__name__).warning(f"Failed to sync topic metadata: {e}")

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

    async def _prepare_execution_context(self: RouterExecutionHost, inbound: InboundMessage) -> _RouterExecutionContext | None:
        """Prepare execution context: identity resolution, session check, topic validation.

        Returns:
            Frozen context or None to skip processing.
            ``exec_msg`` is the inbound message after group-policy transforms (prefix strip, context buffer).
        """
        chat_id = inbound.chat_id or inbound.sender_id
        state_key = routing_session_key(inbound.channel, chat_id)

        if inbound.is_group:
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

        route_agent_id = exec_msg.metadata.get("route_agent_id")
        if isinstance(route_agent_id, str):
            topic_ctx = TopicContext(
                topic_id=exec_msg.thread_id or chat_id,
                agent_id=route_agent_id,
                enabled=True,
                matched_by="alias",
            )
            logger.warning("AgentRouter: routing to agent %s via subcommand", route_agent_id)

        return _RouterExecutionContext(
            user_id=user_id,
            state_key=state_key,
            chat_id=chat_id,
            message_id=message_id,
            topic_ctx=topic_ctx,
            exec_msg=exec_msg,
        )

    async def _setup_message_effects(
        self: RouterExecutionHost,
        msg: InboundMessage,
        state_key: str,
        chat_id: str,
        message_id: str | None,
        is_resume: bool,
    ) -> DeferredPlaceholder | None:
        """Setup message effects: typing/reaction/placeholder, register cleanup.

        Returns:
            DeferredPlaceholder handle or None when placeholder is skipped/disabled
        """
        if not is_resume:
            rp = self._reaction_policy
            if rp.should_processing:
                await self._fx.set_reaction(msg.channel, chat_id, message_id, rp.processing_emoji)

            deferred: DeferredPlaceholder | None = None
            if rp.level != ReactionLevel.OFF:

                async def _send_placeholder() -> str | None:
                    return await self._fx.send_placeholder(msg.channel, chat_id, thread_id=msg.thread_id, msg=msg)

                deferred = DeferredPlaceholder()
                deferred.start(_send_placeholder)

                active = self._active_tasks.get(state_key)
                if active:
                    active.deferred_placeholder = deferred

                async def _track_placeholder() -> None:
                    pid = await deferred.wait_for_id()
                    active_task = self._active_tasks.get(state_key)
                    if active_task and pid:
                        active_task.placeholder_id = pid
                    elif active_task and not pid:
                        await self._fx.set_typing(msg.channel, chat_id, composing=True)
                        self._fx.start_typing_keepalive(msg.channel, chat_id)

                asyncio.create_task(_track_placeholder())

            if not deferred:
                await self._fx.set_typing(msg.channel, chat_id, composing=True)
                self._fx.start_typing_keepalive(msg.channel, chat_id)

            self._register_cleanup(state_key, msg.channel, chat_id, message_id, None, msg=msg)
            return deferred
        else:
            active = self._active_tasks.get(state_key)
            if active and active.deferred_placeholder is not None:
                return active.deferred_placeholder  # type: ignore[return-value]
            return None

    def _resolve_live_placeholder_id(self: RouterExecutionHost, state_key: str) -> str | None:
        active = self._active_tasks.get(state_key)
        if not active:
            return None
        if active.placeholder_id:
            return active.placeholder_id
        deferred = active.deferred_placeholder
        if isinstance(deferred, DeferredPlaceholder):
            return deferred.placeholder_id
        return None

    async def _deliver_agent_result(
        self: RouterExecutionHost,
        result: OutboundMessage | None,
        deferred: DeferredPlaceholder | None,
        msg: InboundMessage,
        chat_id: str,
        last_progress_at: float,
        inbound_had_voice: bool,
    ) -> None:
        """Deliver agent result: TTS processing, edit placeholder or send new message."""
        placeholder_id = await deferred.resolve_for_delivery(result) if deferred else None
        if result:
            result = await maybe_tts(result, inbound_had_voice, self._voice)
            result = with_final_notify(result)
            if placeholder_id:
                await self._fx.wait_for_edit_gap(last_progress_at, _MIN_PROGRESS_INTERVAL)
                await self._fx.edit_placeholder(msg.channel, chat_id, placeholder_id, result)
            else:
                await self._bus.publish_outbound(result)
        elif placeholder_id:
            await self._fx.cleanup_placeholder(
                msg.channel,
                chat_id,
                placeholder_id,
                get_text(msg, "placeholder_no_response"),
            )

    async def _cleanup_effects(
        self: RouterExecutionHost,
        state_key: str,
        chat_id: str,
        channel: str,
        message_id: str | None,
        placeholder_id: str | None,
    ) -> None:
        """Cleanup task registration, callbacks, typing, and reaction.

        Preserves _active_tasks entry when a pending approval exists for this
        session so that numeric shortcut replies (e.g. "1") are correctly
        routed to the approval handler instead of being treated as new messages.
        """
        has_pending_approval = state_key in self._approval_msg_ids
        if not has_pending_approval:
            self._active_tasks.pop(state_key, None)
        self._cleanups.pop(state_key, None)
        if not placeholder_id:
            await self._fx.stop_typing_keepalive(channel, chat_id)
            await self._fx.set_typing(channel, chat_id, composing=False)
        await self._fx.set_reaction(channel, chat_id, message_id, "")

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
        self._active_tasks[ctx.state_key] = _ActiveTask(
            task=current_task,
            cancel_token=cancel_token,
            channel=ctx.exec_msg.channel,
            chat_id=ctx.chat_id,
            placeholder_id=None,
            requester_id=ctx.exec_msg.sender_id or "",
            steering_token=steering_token,
        )

        scratch.deferred_placeholder = await self._setup_message_effects(
            ctx.exec_msg,
            ctx.state_key,
            ctx.chat_id,
            ctx.message_id,
            is_resume,
        )

        try:
            result, last_progress_at = await self._consume_executor_stream(
                ctx.exec_msg,
                ctx.user_id,
                ctx.state_key,
                ctx.chat_id,
                cancel_token=cancel_token,
                steering_token=steering_token,
                topic_context=ctx.topic_ctx if not is_resume else None,
            )
            deferred = scratch.deferred_placeholder if isinstance(scratch.deferred_placeholder, DeferredPlaceholder) else None
            await self._deliver_agent_result(
                result,
                deferred,
                ctx.exec_msg,
                ctx.chat_id,
                last_progress_at,
                inbound_had_voice,
            )
            scratch.completed = True
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
                            error=str(inner_exc)[:200],
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
                ctx.message_id,
                placeholder_id,
            )

    def _register_cleanup(
        self: RouterExecutionHost,
        key: str,
        channel: str,
        chat_id: str,
        message_id: object,
        placeholder_id: str | None = None,
        *,
        msg: InboundMessage | None = None,
    ) -> None:
        """Register cleanup closures for TTL janitor eviction."""

        async def _do_cleanup() -> None:
            if placeholder_id:
                timeout_text = (
                    get_text(msg, "placeholder_request_timeout")
                    if msg is not None
                    else channel_t(None, "placeholder_request_timeout")
                )
                await self._fx.cleanup_placeholder(
                    channel,
                    chat_id,
                    placeholder_id,
                    timeout_text,
                )
            await self._fx.stop_typing_keepalive(channel, chat_id)
            await self._fx.set_typing(channel, chat_id, composing=False)
            await self._fx.set_reaction(channel, chat_id, message_id, "")

        self._cleanups[key] = _CleanupEntry(
            cleanup=_do_cleanup,
            created_at=time.monotonic(),
        )
