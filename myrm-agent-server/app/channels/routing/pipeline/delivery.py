"""Router delivery mixin: a turn's outbound side effects, from the typing indicator to the delivered reply.

[INPUT]
- channels.routing.pipeline.hosts::RouterDeliveryHost (POS: typing protocol for the host attributes this mixin reads)
- channels.routing.placeholder_strategy::DeferredPlaceholder (POS: adaptive placeholder timing, deferred for fast short replies)
- channels.routing.router_constants::_MIN_PROGRESS_INTERVAL, _is_silent_content (POS: edit pacing and the silent-reply test)
- channels.routing.router_models::_CleanupEntry (POS: janitor cleanup record)
- channels.core.outbound_media::discard_ephemeral_media (POS: drop media of a reply that is not sent)
- channels.voice.handler::maybe_tts (POS: spoken reply when the inbound message was a voice message)
- channels.types.notification::with_final_notify (POS: final-reply notification flag)
- channels.i18n::channel_t, get_text, resolve_message_locale (POS: localized channel copy)

[OUTPUT]
- RouterDeliveryMixin: ``_setup_message_effects`` (deferred placeholder, typing, cleanup registration), ``_deliver_agent_result`` (silent filter, web handoff button, TTS, draft review hold, placeholder edit or new message, data-plane record), ``_create_outbound_draft`` (held reply as an approval), ``_cleanup_effects``, ``_register_cleanup`` (TTL janitor closure), ``_resolve_live_placeholder_id`` and ``_attach_web_handoff``

[POS]
Delivery segment of ``AgentRouter``. A reply that draft review holds is never sent unreviewed: when it cannot be held it is withheld.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import time

from app.channels.core.outbound_media import discard_ephemeral_media
from app.channels.i18n import channel_t, get_text, resolve_message_locale
from app.channels.routing.pipeline.hosts import RouterDeliveryHost
from app.channels.routing.placeholder_strategy import (
    DeferredPlaceholder,
)
from app.channels.routing.router_constants import (
    _MIN_PROGRESS_INTERVAL,
    _is_silent_content,
)
from app.channels.routing.router_models import _CleanupEntry
from app.channels.types import (
    InboundMessage,
    OutboundMessage,
    ReactionLevel,
    TopicContext,
)
from app.channels.types.notification import with_final_notify
from app.channels.voice.handler import maybe_tts

logger = logging.getLogger("app.channels.routing.router")


class RouterDeliveryMixin:
    """Mixin: placeholder, typing and reaction effects and the delivery of a turn's reply."""

    async def _setup_message_effects(
        self: RouterDeliveryHost,
        msg: InboundMessage,
        state_key: str,
        chat_id: str,
        message_id: str | None,
        is_resume: bool,
    ) -> DeferredPlaceholder | None:
        """Setup message effects: typing/placeholder, register cleanup (the processing reaction is set by the turn).

        Returns:
            DeferredPlaceholder handle or None when placeholder is skipped/disabled
        """
        if not is_resume:
            rp = self._reaction_policy
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
            placeholder = active.deferred_placeholder if active else None
            return placeholder if isinstance(placeholder, DeferredPlaceholder) else None

    def _resolve_live_placeholder_id(self: RouterDeliveryHost, state_key: str) -> str | None:
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
        self: RouterDeliveryHost,
        result: OutboundMessage | None,
        deferred: DeferredPlaceholder | None,
        msg: InboundMessage,
        chat_id: str,
        last_progress_at: float,
        inbound_had_voice: bool,
        topic_ctx: TopicContext | None = None,
    ) -> bool:
        """Deliver agent result: TTS processing, edit placeholder or send new message.

        When ``topic_ctx.reply_mode`` is ``draft_review``, the outbound message
        is held as an ApprovalRecord instead of being sent immediately; a reply
        that cannot be held is withheld, never sent unreviewed.

        Returns True when the result was actually sent to the channel.
        """
        placeholder_id = await deferred.resolve_for_delivery(result) if deferred else None

        if result and _is_silent_content(result.content):
            discard_ephemeral_media(result.media)
            if placeholder_id:
                await self._fx.cleanup_placeholder(msg.channel, chat_id, placeholder_id, "\u200b")
            return False

        if result:
            if msg.channel != "web":
                result = await self._attach_web_handoff(result, msg)
            result = await maybe_tts(result, inbound_had_voice, self._voice)
            result = with_final_notify(result)

            if topic_ctx is not None and topic_ctx.holds_reply_for_review:
                try:
                    await self._create_outbound_draft(result, msg, chat_id, topic_ctx, placeholder_id)
                except Exception:
                    # Fail closed: draft review promises that no reply is sent before a human approved it.
                    logger.exception("Failed to hold the reply for review, withholding it")
                    discard_ephemeral_media(result.media)
                    if placeholder_id:
                        await self._fx.cleanup_placeholder(msg.channel, chat_id, placeholder_id, "\u200b")
                    return False
                if placeholder_id:
                    await self._fx.cleanup_placeholder(
                        msg.channel,
                        chat_id,
                        placeholder_id,
                        get_text(msg, "draft_review_pending"),
                    )
                return False

            if placeholder_id:
                await self._fx.wait_for_edit_gap(last_progress_at, _MIN_PROGRESS_INTERVAL)
                await self._fx.edit_placeholder(msg.channel, chat_id, placeholder_id, result)
            else:
                await self._bus.publish_outbound(result)

            from app.channels.routing.channel_data_plane import ChannelDataPlaneService

            asyncio.create_task(
                ChannelDataPlaneService.record_outbound(
                    channel=msg.channel,
                    chat_id=chat_id,
                    content=str(result.content or ""),
                    thread_id=msg.thread_id,
                    reply_to_id=result.reply_to_id,
                )
            )
            return True
        elif placeholder_id:
            await self._fx.cleanup_placeholder(
                msg.channel,
                chat_id,
                placeholder_id,
                get_text(msg, "placeholder_no_response"),
            )
        return False

    async def _create_outbound_draft(
        self: RouterDeliveryHost,
        result: OutboundMessage,
        original_msg: InboundMessage,
        chat_id: str,
        topic_ctx: TopicContext,
        placeholder_id: str | None,
    ) -> None:
        """Hold an outbound message as a draft approval for human review.

        ``placeholder_id`` is the message the sender sees while the reply is held; it travels with the draft so that
        whoever decides on it can close that message.
        """
        from datetime import datetime, timedelta, timezone

        from app.services.approvals.registry import ApprovalRegistry

        timeout_min = max(1, topic_ctx.draft_timeout_minutes)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=timeout_min)

        payload: dict[str, object] = {
            "draft_content": result.content,
            # Everything but the text, which is read from ``draft_content`` when the reply is sent.
            "outbound": dataclasses.replace(result, content="").to_dict(),
            "channel": result.channel,
            "recipient_id": result.recipient_id,
            "placeholder_id": placeholder_id,
            "original_sender_id": original_msg.sender_id,
            "original_content": (original_msg.content or "")[:500],
            "topic_id": topic_ctx.topic_id,
            "draft_timeout_action": topic_ctx.draft_timeout_action.value,
        }

        agent_id = topic_ctx.agent_id or "default"

        await ApprovalRegistry.create_approval(
            agent_id=agent_id,
            action_type="outbound_draft",
            payload=payload,
            reason=get_text(original_msg, "draft_review_reason"),
            severity="info",
            chat_id=chat_id,
            expires_at=expires_at,
        )
        logger.info(
            "Outbound draft created for %s/%s (timeout=%dm, action=%s)",
            original_msg.channel,
            chat_id,
            topic_ctx.draft_timeout_minutes,
            topic_ctx.draft_timeout_action.value,
        )

    async def _cleanup_effects(
        self: RouterDeliveryHost,
        state_key: str,
        chat_id: str,
        channel: str,
        placeholder_id: str | None,
    ) -> None:
        """Cleanup task registration, callbacks and typing; the status reaction is settled by the turn.

        Preserves _active_tasks entry when a pending approval exists for this
        session so that numeric shortcut replies (e.g. "1") are correctly
        routed to the approval handler instead of being treated as new messages.
        """
        if state_key not in self._pending_approvals:
            self._active_tasks.pop(state_key, None)
        self._cleanups.pop(state_key, None)
        if not placeholder_id:
            await self._fx.stop_typing_keepalive(channel, chat_id)
            await self._fx.set_typing(channel, chat_id, composing=False)

    def _register_cleanup(
        self: RouterDeliveryHost,
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

    @staticmethod
    async def _attach_web_handoff(
        result: OutboundMessage,
        msg: InboundMessage,
    ) -> OutboundMessage:
        """Append a SECONDARY "Continue in browser" button for IM channel replies.

        The Chat row is resolved from ``msg`` (channel, peer and forum topic), so the deep link
        points to a valid ``/{chatUUID}`` frontend route. Failures are swallowed so the main
        reply is never blocked.
        """
        try:
            from app.core.channel_bridge.agent_executor.session import (
                build_channel_session_key,
            )
            from app.remote_access.mobile_deep_link import (
                resolve_web_handoff_components,
            )
            from app.services.chat.chat_service import ChatService

            # ``Chat.channel_session_key`` is channel + peer_kind + peer + topic (+ agent) plus a
            # reset epoch. Resolve the key the agent executor stored; older rows written before
            # peer_kind entered the format still answer to the bare channel:peer key.
            session_key = build_channel_session_key(msg)
            chat = await ChatService.get_channel_chat_by_key(session_key)
            if chat is None:
                # The stored key appends the bound agent and a reset epoch.
                chat = await ChatService.get_newest_channel_chat_under(session_key)
            if chat is None:
                # Rows written with only channel + peer (no peer_kind segment) answer here.
                bare_key = f"{msg.channel}:{msg.chat_id if msg.is_group and msg.chat_id else msg.sender_id}"
                chat = await ChatService.get_newest_channel_chat_under(bare_key)
            if not chat:
                return result
            locale = resolve_message_locale(msg)
            handoff_rows = await resolve_web_handoff_components(chat.id, locale=locale)
            if not handoff_rows:
                return result
            return dataclasses.replace(
                result,
                components=result.components + handoff_rows,
            )
        except Exception:
            logger.debug("Failed to attach web handoff button, skipping", exc_info=True)
            return result
