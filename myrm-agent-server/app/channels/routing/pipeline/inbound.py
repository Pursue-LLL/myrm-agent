"""Router inbound mixin: what happens to one consumed message before it reaches the session gate.

[INPUT]
- channels.routing.pipeline.hosts::RouterInboundHost (POS: typing protocol for the host attributes this mixin reads)
- channels.routing.commands::is_explicit_approval_command, parse_approval_command (POS: approval shortcut parsing)
- channels.routing.inbound_risk_gate::hold_risky_inbound (POS: risk screening of a sender's text before any agent reads it)
- channels.routing.policy_resolver_support::is_admin_sender (POS: the owner rule for admin-only commands)
- channels.routing.router_constants::_DEDUP_MAX_SIZE, _DEDUP_TTL (POS: dedup window limits)
- channels.routing.router_keys::routing_state_key (POS: channel+peer+topic state-map key format)
- channels.delegation::is_delegation_intent (POS: detection of a delegated-task request)
- core.cron.adapters.inbound_event_dispatch::dispatch_cron_event_for_inbound_message (POS: event triggers that start unattended jobs)
- channels.i18n::get_text, resolve_message_locale (POS: localized channel copy)
- channels.types::InboundMessage, OutboundMessage (POS: channel message envelopes)

[OUTPUT]
- RouterInboundMixin: ``_dispatch_inbound_message``, the sequence of steps one message passes (dedup, group activity, locale, then the steps that may claim it: ``_claim_approval_input``, ``_claim_command``, ``_claim_delegation``, ``_claim_delegated_task_steering``, with ``_fire_event_triggers`` between the commands and the delegation, then ``_divert_group_chatter``, and finally the session gate); the sender checks (``_check_admin_permission``, ``_is_sender_admitted``, ``_is_untrusted_event_sender``, all fail closed), ``_enrich_message_locale`` and ``_is_duplicate``

[POS]
Inbound segment of ``AgentRouter``. Runs on the consume loop, one message at a time, so every check here must either finish fast or hand off to a task.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import time

from myrm_agent_harness.utils.locale import resolve_locale

from app.channels.delegation import is_delegation_intent
from app.channels.i18n import get_text, resolve_message_locale
from app.channels.routing.commands import is_explicit_approval_command, parse_approval_command
from app.channels.routing.inbound_risk_gate import hold_risky_inbound
from app.channels.routing.pipeline.hosts import RouterInboundHost
from app.channels.routing.policy_resolver_support import is_admin_sender
from app.channels.routing.router_constants import _DEDUP_MAX_SIZE, _DEDUP_TTL
from app.channels.routing.router_keys import routing_state_key
from app.channels.types import InboundMessage, OutboundMessage
from app.core.cron.adapters.inbound_event_dispatch import dispatch_cron_event_for_inbound_message

logger = logging.getLogger("app.channels.routing.router")

_DELEGATION_MIN_CONFIDENCE = 0.85


class RouterInboundMixin:
    """Mixin: dedup, sender checks, locale, and the routing of one consumed inbound message."""

    async def _dispatch_inbound_message(self: RouterInboundHost, msg: InboundMessage) -> None:
        """Route one consumed message; the consume loop survives a failure here.

        Each step either claims the message, which ends the dispatch, or leaves it for the next; what no step claims
        reaches the session gate and becomes a turn.
        """
        if self._is_duplicate(msg):
            logger.debug(
                "Duplicate message %s from %s, skipping",
                msg.message_id,
                msg.channel,
            )
            return

        self._note_group_activity(msg)
        msg = await self._enrich_message_locale(msg)

        # NOTE: inbound ledger persistence is single-sourced in PolicyResolver
        # (group non-trigger / group trigger / DM trigger) with the resolved
        # is_trigger semantics. A second unconditional write here would race
        # those records and permanently mislabel observed messages as triggers.

        if self._claim_approval_input(msg) or await self._claim_command(msg):
            return
        await self._fire_event_triggers(msg)
        if await self._claim_delegation(msg) or await self._claim_delegated_task_steering(msg):
            return
        if await self._divert_group_chatter(msg):
            return
        self._gate.submit(msg)

    def _note_group_activity(self: RouterInboundHost, msg: InboundMessage) -> None:
        """Record who spoke in a group's topic and look for threads that have gone quiet."""
        if not msg.is_group or self._topic_resolver is None:
            return
        from app.channels.routing.channel_data_plane import ChannelDataPlaneService
        from app.channels.routing.follow_up import note_group_activity, scan_stalled_threads

        note_group_activity(
            msg.channel,
            msg.chat_id or msg.sender_id,
            msg.thread_id,
            msg.sender_id,
            msg.sender_name,
            resolve_message_locale(msg),
        )
        asyncio.create_task(
            scan_stalled_threads(
                bus=self._bus,
                resolve_topic=self._topic_resolver.resolve_topic,
                record_outbound=ChannelDataPlaneService.record_outbound,
            )
        )

    def _claim_approval_input(self: RouterInboundHost, msg: InboundMessage) -> bool:
        """Hand an answer to an approval (a button click, a reaction, a typed word) to the approval handlers.

        A reaction never starts a turn, so one that answers no open request is dropped here.
        """
        if msg.metadata.get("callback_prefix") == "act" and isinstance(msg.content, str) and msg.content.startswith("approval:"):
            asyncio.create_task(self._handle_action_button_approval(msg))
            return True

        approval_cmd = parse_approval_command(msg.content)
        if msg.metadata.get("reaction"):
            if approval_cmd is not None and self._is_reaction_approval_valid(msg):
                asyncio.create_task(self._handle_approval_command(msg, approval_cmd))
            return True

        if approval_cmd is not None and (is_explicit_approval_command(msg.content) or self._has_pending_approval(msg)):
            asyncio.create_task(self._handle_approval_command(msg, approval_cmd))
            return True
        return False

    async def _claim_command(self: RouterInboundHost, msg: InboundMessage) -> bool:
        """Run a slash command the registry knows, or answer a raw shell command."""
        resolved = self._registry.resolve(msg.content)
        if resolved is not None and await self._dispatch_resolved(msg, resolved):
            return True
        if self._is_bang_command(msg.content):
            asyncio.create_task(self._handle_bang_command(msg))
            return True
        return False

    async def _fire_event_triggers(self: RouterInboundHost, msg: InboundMessage) -> None:
        """Start the jobs whose event trigger this message matches. Never claims the message.

        Event triggers start unattended jobs on the owner's account, so they follow the same sender policy and the same
        tool fence as a chat turn from that sender. The resolvers that enforce both run later and have side effects,
        hence the read-only checks.
        """
        if await self._is_sender_admitted(msg):
            await dispatch_cron_event_for_inbound_message(
                msg.content,
                msg.channel,
                msg.user_id or "",
                untrusted=await self._is_untrusted_event_sender(msg),
            )

    async def _divert_group_chatter(self: RouterInboundHost, msg: InboundMessage) -> bool:
        """Settle group chatter that arrives while the chat's turn runs, instead of queueing it behind that turn.

        Queued, it would take one of the pending slots, make the chat read "Agent is busy, your message has been queued"
        for a message nobody addressed to the bot, and still end as context for the next turn. Only text qualifies:
        the attachments of a queued message are processed before the trigger is decided, and their text is context
        too. Fails open: an error here queues the message as it always was.
        """
        if not (msg.is_group and msg.content and not msg.media and msg.resume_value is None and self._gate.is_busy(msg)):
            return False
        try:
            return await self._resolver.divert_group_chatter(msg)
        except Exception:
            logger.warning("Chatter check failed for %s/%s, queueing the message", msg.channel, msg.chat_id, exc_info=True)
            return False

    async def _claim_delegation(self: RouterInboundHost, msg: InboundMessage) -> bool:
        """Start a delegated task when the owner asks for one (mobile-to-desktop asynchronous delegation).

        A delegated run and its in-flight steering skip the per-turn identity pipeline (no DM policy, no
        untrusted-ingress fence), so only the owner may use them; anyone else's message continues as an ordinary turn.
        """
        if not msg.content or not isinstance(msg.content, str):
            return False
        is_delegated, confidence, clean_prompt = is_delegation_intent(msg.content)
        if not (is_delegated and confidence >= _DELEGATION_MIN_CONFIDENCE and await self._check_admin_permission(msg)):
            return False
        if not clean_prompt:
            self._reply_in_background(msg, get_text(msg, "delegation_task_missing"))
            return True
        if await hold_risky_inbound(self._bus, msg, clean_prompt):
            return True
        return await self._handle_delegation_inbound(msg, clean_prompt)

    async def _claim_delegated_task_steering(self: RouterInboundHost, msg: InboundMessage) -> bool:
        """Pass the owner's text on to the delegated task running for them in this chat, while no turn of the chat runs."""
        chat_id = msg.chat_id or msg.sender_id
        user_id = msg.user_id or msg.sender_id
        task = self._delegation_coordinator.find_active_task(msg.channel, chat_id, user_id)
        if not (
            task
            and msg.content
            and isinstance(msg.content, str)
            and not msg.content.startswith("/")
            and not self._active_tasks.get(routing_state_key(msg.channel, chat_id, msg.thread_id))
            and await self._check_admin_permission(msg)
        ):
            return False
        if await hold_risky_inbound(self._bus, msg, msg.content):
            return True
        if not self._delegation_coordinator.inject_steering(task.task_id, msg.content.strip(), user_id):
            return False
        self._reply_in_background(msg, get_text(msg, "delegation_steering_injected", task_id=task.task_id))
        return True

    def _reply_in_background(self: RouterInboundHost, msg: InboundMessage, content: str, *, quote_in_group: bool = False) -> None:
        """Answer the sender from a task, so the consume loop does not wait for the channel to take the reply."""
        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=msg.chat_id or msg.sender_id,
            content=content,
            user_id=msg.user_id or "",
            thread_id=msg.thread_id,
            reply_to_id=(msg.message_id or str(msg.metadata.get("message_id", ""))) if quote_in_group and msg.is_group else None,
        )
        asyncio.create_task(self._bus.publish_outbound(reply))

    async def _enrich_message_locale(self: RouterInboundHost, msg: InboundMessage) -> InboundMessage:
        """Inject resolved locale into inbound message metadata."""
        meta = dict(msg.metadata) if msg.metadata else {}
        if meta.get("locale"):
            return msg

        platform_locale: str | None = None
        channel = self._bus.get_channel(msg.channel)
        if channel is not None:
            platform_locale = channel.extract_sender_locale(msg)
            if platform_locale:
                meta["platform_locale"] = platform_locale

        user_locale: str | None = None
        if self._locale_provider is not None:
            user_locale = await self._locale_provider.resolve_locale(msg)

        locale = resolve_locale(
            metadata_locale=str(meta["locale"]) if meta.get("locale") else None,
            platform_locale=platform_locale,
            user_locale=user_locale,
            channel=msg.channel,
        )
        meta["locale"] = locale
        return dataclasses.replace(msg, metadata=meta)

    async def _check_admin_permission(self: RouterInboundHost, msg: InboundMessage) -> bool:
        """Whether the sender is the sandbox owner, which owner-only commands, delegation and held-reply decisions need.

        A DM sender is not automatically the owner: an open DM policy admits any account. Fails closed: an error
        here would end the dispatch before the session gate and drop the message, and must never grant access.
        """
        try:
            return await is_admin_sender(self._resolver.pairing, msg)
        except Exception:
            logger.warning("Admin check failed for %s/%s, denying", msg.channel, msg.sender_id, exc_info=True)
            return False

    async def _is_sender_admitted(self: RouterInboundHost, msg: InboundMessage) -> bool:
        """Whether the access policy admits the sender.

        Fails closed: an error here would end the dispatch before the session gate and drop the message, so a
        failed check only skips the event triggers.
        """
        try:
            return await self._resolver.is_sender_admitted(msg)
        except Exception:
            logger.warning("Admission check failed for %s/%s, denying", msg.channel, msg.sender_id, exc_info=True)
            return False

    async def _is_untrusted_event_sender(self: RouterInboundHost, msg: InboundMessage) -> bool:
        """Whether a job this sender's message starts runs under the tool fence of an untrusted chat turn.

        Fails closed (the sender counts as untrusted): an error here would end the dispatch before the session gate
        and drop the message.
        """
        try:
            return await self._resolver.is_untrusted_event_sender(msg)
        except Exception:
            logger.warning("Trust check failed for %s/%s, treating as untrusted", msg.channel, msg.sender_id, exc_info=True)
            return True

    def _is_duplicate(self: RouterInboundHost, msg: InboundMessage) -> bool:
        """Check if a message has already been processed (TTL-based dedup).

        Dedup key includes the channel name to prevent cross-channel ID collisions
        (e.g. Telegram's numeric message_id vs WhatsApp's string ID).
        """
        if not msg.message_id:
            return False

        dedup_key = f"{msg.channel}:{msg.message_id}"
        now = time.monotonic()

        if dedup_key in self._seen_messages:
            return True

        self._seen_messages[dedup_key] = now

        if len(self._seen_messages) > _DEDUP_MAX_SIZE:
            cutoff = now - _DEDUP_TTL
            self._seen_messages = {k: v for k, v in self._seen_messages.items() if v > cutoff}

        return False
