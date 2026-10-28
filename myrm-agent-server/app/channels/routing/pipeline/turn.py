"""Router turn mixin: one (possibly merged) message from the session gate to the agent run.

[INPUT]
- channels.routing.pipeline.hosts::RouterTurnHost (POS: typing protocol for the host attributes and execution steps this mixin uses)
- channels.routing.command_defs::CommandKind (POS: slash command enums)
- channels.routing.commands::parse_topic_args (POS: slash command argument parsing)
- channels.routing.inbound_risk_gate::hold_risky_inbound (POS: risk screening of a sender's text before any agent reads it)
- channels.routing.router_models::_AgentTurnScratch (POS: per-turn state the error path reads)
- channels.routing.reactions::StatusReaction, TurnOutcome (POS: the reaction the turn shows on the user's message)
- channels.voice.handler::transcribe_inbound, transcribe_video_inbound, has_audio_attachment, has_video_with_audio (POS: voice processing)
- channels.media.*::image, video, contact, document and sticker enrichment (POS: attachment enrichment before the agent reads the message)
- channels.core.outbound_prepare::set_correlation_context (POS: correlation context of the turn's outbound messages)
- channels.types.topics::METADATA_ROUTE_AGENT_KEY (POS: alias route marker)

[OUTPUT]
- RouterTurnMixin: ``_handle_merged`` (the SessionGate ``on_ready`` entry: ``_journal_inbound``, ``_apply_session_state``, ``_enrich_attachments``, the risk gate, ``_apply_agent_route``, then prepare and execute the turn under the concurrency semaphore, with ``_report_turn_failure`` as the friendly error path) and ``_acknowledge_inbound``

[POS]
Turn segment of ``AgentRouter``. The journal entry is acknowledged on every way out and the gate is told the turn is done, which also drains the messages queued behind it. The turn owns the status reaction of the message: it starts marking the message as the run begins, without waiting for the platform, and settles the mark once, after the run or in the error path.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import time

from app.channels.core.outbound_prepare import set_correlation_context
from app.channels.media.contact_enrichment import (
    enrich_contact_inbound,
    has_contact_attachment,
)
from app.channels.media.document_enrichment import (
    enrich_document_inbound,
    has_document_attachment,
)
from app.channels.media.image_enrichment import (
    enrich_image_inbound,
)
from app.channels.media.image_enrichment import (
    has_image_attachment as has_image_attachment_fn,
)
from app.channels.media.sticker_vision import describe_sticker_inbound
from app.channels.media.video_enrichment import (
    enrich_video_inbound,
)
from app.channels.media.video_enrichment import (
    has_video_attachment as has_video_attachment_fn,
)
from app.channels.reliability.inbound_journal import create_journal_entry_from_inbound
from app.channels.routing.command_defs import CommandKind
from app.channels.routing.commands import parse_topic_args
from app.channels.routing.friendly_errors import friendly_error_message
from app.channels.routing.inbound_risk_gate import hold_risky_inbound
from app.channels.routing.pipeline.hosts import RouterTurnHost
from app.channels.routing.placeholder_strategy import DeferredPlaceholder
from app.channels.routing.reactions import StatusReaction, TurnOutcome
from app.channels.routing.router_keys import routing_state_key
from app.channels.routing.router_models import _AgentTurnScratch
from app.channels.types import InboundMessage
from app.channels.types.topics import METADATA_ROUTE_AGENT_KEY
from app.channels.voice.handler import (
    has_audio_attachment,
    has_video_with_audio,
    transcribe_inbound,
    transcribe_video_inbound,
)

logger = logging.getLogger("app.channels.routing.router")


class RouterTurnMixin:
    """Mixin: the turn a session gate hands over, from journal and enrichment to the agent run."""

    def _acknowledge_inbound(self: RouterTurnHost, journal_entry_id: str | None) -> None:
        """Delete the journal entry of a message that needs no replay: it was handled, or held by the risk gate."""
        if self._inbound_journal and journal_entry_id:
            self._inbound_journal.acknowledge(journal_entry_id)

    async def _handle_merged(self: RouterTurnHost, msg: InboundMessage) -> None:
        """Process a (possibly merged) inbound message with concurrency control.

        Called by SessionGate after debounce timer expires or pending queue drains.
        The journal entry is acknowledged on every way out: the early returns before the ``try`` do it themselves, the
        ``finally`` covers the rest (and notifies the gate, which also drains pending messages once this returns).

        ``exec_for_error`` is the InboundMessage passed to ``send_error_reply`` and
        used for ``channel`` on the outer ``cleanup_placeholder`` path: it matches
        ``msg`` after attachment enrichment (voice transcription included), and ``ctx.exec_msg``
        after ``_prepare_execution_context`` succeeds. Successful ``prepare`` hands
        off to ``_execute_prepared_context`` (active task registration, stream, delivery).
        """
        journal_entry_id = self._journal_inbound(msg)
        msg = self._apply_session_state(msg)

        scratch = _AgentTurnScratch()
        status: StatusReaction | None = None
        chat_id: str = ""
        is_resume = bool(msg.resume_value)
        inbound_had_voice = has_audio_attachment(msg) if not is_resume else False

        msg = await self._enrich_attachments(msg, is_resume=is_resume, inbound_had_voice=inbound_had_voice)
        exec_for_error: InboundMessage = msg

        if not is_resume and msg.content and await hold_risky_inbound(self._bus, msg, msg.content):
            self._acknowledge_inbound(journal_entry_id)
            return

        routed = self._apply_agent_route(msg)
        if routed is None:
            self._acknowledge_inbound(journal_entry_id)
            return
        msg = routed

        try:
            async with self._semaphore:
                try:
                    ctx = await self._prepare_execution_context(msg)
                    if ctx is None:
                        return

                    chat_id = ctx.chat_id
                    exec_for_error = ctx.exec_msg
                    if not is_resume:
                        await self._retire_open_approval(ctx)

                    status = StatusReaction(self._fx, self._reaction_policy, msg.channel, chat_id, msg.message_id)
                    status.received()

                    await self._execute_prepared_context(
                        ctx,
                        scratch,
                        is_resume=is_resume,
                        inbound_had_voice=inbound_had_voice,
                    )

                    await status.finish(TurnOutcome.COMPLETED if scratch.completed else TurnOutcome.ABANDONED)

                except Exception as e:
                    await self._report_turn_failure(
                        e, msg=msg, exec_for_error=exec_for_error, chat_id=chat_id, scratch=scratch, status=status
                    )
        finally:
            if status is not None:
                status.cancel()
            self._acknowledge_inbound(journal_entry_id)
            self._gate.on_task_complete(msg)

    def _journal_inbound(self: RouterTurnHost, msg: InboundMessage) -> str | None:
        """Write the message to the inbound journal and return the id of the entry to acknowledge afterwards.

        A message replayed after a restart has its entry already: it is neither written again nor, without an entry
        id, acknowledged.
        """
        if self._inbound_journal and not msg.metadata.get("is_recovery"):
            entry = create_journal_entry_from_inbound(msg)
            self._inbound_journal.write(entry)
            return entry.id
        if self._inbound_journal and msg.metadata.get("recovery_entry_id"):
            return str(msg.metadata["recovery_entry_id"])
        return None

    def _apply_session_state(self: RouterTurnHost, msg: InboundMessage) -> InboundMessage:
        """Put what the channel and the session decided onto the message: capabilities, the yolo window, the personality.

        An expired yolo window is dropped from the session here, the one place that reads it.
        """
        channel_instance = self._bus.get_channel(msg.channel)
        if channel_instance and msg.channel_capabilities is None:
            msg = dataclasses.replace(msg, channel_capabilities=channel_instance.capabilities)

        chat_id = msg.chat_id or msg.sender_id
        session_key = routing_state_key(msg.channel, chat_id, msg.thread_id)
        yolo_state = self._session_yolo.get(session_key)
        if yolo_state:
            enabled_at, timeout = yolo_state
            if timeout:
                elapsed = time.time() - enabled_at
                if elapsed < timeout:
                    msg.metadata["yolo_state"] = (enabled_at, timeout)
                else:
                    del self._session_yolo[session_key]
            else:
                msg.metadata["yolo_state"] = (enabled_at, None)

        session_personality = self._session_personality.get(session_key)
        if session_personality:
            msg.metadata["personality_style"] = session_personality
        return msg

    async def _enrich_attachments(
        self: RouterTurnHost, msg: InboundMessage, *, is_resume: bool, inbound_had_voice: bool
    ) -> InboundMessage:
        """Turn the attachments of a new turn into text the agent can read: transcripts, descriptions, extracted text.

        The answer to an approval carries no new attachments, so only a sticker is described then.
        """
        if inbound_had_voice:
            msg = await transcribe_inbound(msg, self._voice, self._bus.get_channel)

        if msg.metadata.get("is_sticker") and self._sticker_vision:
            msg = await describe_sticker_inbound(msg, self._sticker_vision, self._bus.get_channel)

        if is_resume:
            return msg

        if has_video_attachment_fn(msg):
            msg = enrich_video_inbound(msg)
            if has_video_with_audio(msg):
                msg = await transcribe_video_inbound(msg, self._voice, self._bus.get_channel)

        if has_image_attachment_fn(msg):
            msg = await enrich_image_inbound(msg, self._bus.get_channel)

        if has_contact_attachment(msg):
            msg = await enrich_contact_inbound(msg)

        if has_document_attachment(msg):
            from app.core.channel_bridge.config_loader import load_user_configs
            from app.services.files.attachment_settings import (
                should_extract_document_text,
            )

            configs = await load_user_configs()
            extract_docs = should_extract_document_text(configs.personal_settings_dict)
            msg = await enrich_document_inbound(
                msg,
                self._bus.get_channel,
                extract_enabled=extract_docs,
            )
        return msg

    def _apply_agent_route(self: RouterTurnHost, msg: InboundMessage) -> InboundMessage | None:
        """Rewrite an agent-route alias (``/claude do this``) into a turn on that agent.

        An alias with no request binds the chat to the agent instead, which ends the turn: ``None`` then.
        """
        resolved = self._registry.resolve(msg.content)
        if not resolved or resolved.command_def.kind != CommandKind.AGENT_ROUTE:
            return msg
        agent_id = resolved.command_def.agent_id or resolved.command_def.name
        if resolved.raw_args:
            msg = dataclasses.replace(msg, content=resolved.raw_args)
            msg.metadata[METADATA_ROUTE_AGENT_KEY] = agent_id
            return msg
        asyncio.create_task(self._handle_topic_command(msg, parse_topic_args("bind", agent_id)))
        set_correlation_context(None)
        return None

    async def _report_turn_failure(
        self: RouterTurnHost,
        error: Exception,
        *,
        msg: InboundMessage,
        exec_for_error: InboundMessage,
        chat_id: str,
        scratch: _AgentTurnScratch,
        status: StatusReaction | None,
    ) -> None:
        """Tell the chat the turn failed, in words that carry a reference and no internals: placeholder, reply, reaction.

        The words come first: they are what the user needs, and a platform slow to take the reaction must not delay them.
        A turn that failed before it had a chat has no status reaction yet; the failure is still shown on the message.
        """
        friendly, ref_id = friendly_error_message(error, msg=exec_for_error)
        logger.error(
            "AgentRouter: failed to handle message from %s/%s [ref: %s]: %s",
            exec_for_error.channel,
            exec_for_error.sender_id,
            ref_id,
            error,
            exc_info=error,
        )
        resolved_placeholder: str | None = None
        if isinstance(scratch.deferred_placeholder, DeferredPlaceholder):
            resolved_placeholder = await scratch.deferred_placeholder.wait_for_id()
        if resolved_placeholder and chat_id:
            await self._fx.cleanup_placeholder(
                exec_for_error.channel,
                chat_id,
                resolved_placeholder,
                friendly,
            )
        await self._fx.send_error_reply(exec_for_error, friendly)
        verdict = status or StatusReaction(self._fx, self._reaction_policy, exec_for_error.channel, chat_id, msg.message_id)
        await verdict.finish(TurnOutcome.FAILED)
