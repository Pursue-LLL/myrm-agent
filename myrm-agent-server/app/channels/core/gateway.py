"""Channel Gateway — lifecycle manager for all channel providers.

Manages channel start/stop, inbound crash recovery, and optionally the AgentRouter for bidirectional communication.
The registry and runtime instance management are ``ChannelInstancesMixin`` (``gateway_instances.py``); health supervision
and backoff restarts are ``ChannelHealthMixin`` (``gateway_health.py``).

[INPUT]
- channels.core.bus::MessageBus (POS: async message bus)
- channels.core.gateway_instances::ChannelInstancesMixin (POS: the registry, runtime instance management and health supervision this gateway inherits)
- channels.core.outbound_media::discard_ephemeral_media (POS: drop the temp attachments of a follow-up that cannot be delivered)
- channels.reliability.inbound_journal::InboundJournal, restore_inbound (POS: interrupted-message persistence, and the rebuild of a journal entry into the message to replay)
- channels.routing.router::AgentRouter (POS: inbound message routing hub)
- channels.routing.command_defs::CommandDef (POS: slash command data model)
- channels.types::ChannelStatus, MediaAttachment, OutboundMessage (POS: channel status, and the attachments and messages the gateway publishes)
- channels.protocols.agent::AgentExecutor (POS: agent execution protocol)
- channels.protocols.compact::CompactHandler (POS: /compact business-layer handling protocol)
- channels.protocols.pairing::PairingStore (POS: identity binding protocol)

[OUTPUT]
- ChannelGateway: singleton gateway managing all channel lifecycles; ``deliver_followup`` hands the router a reply (with
  its attachments) no message just asked for, and ``is_session_busy`` says whether a conversation is running a turn

[POS]
Channel system entry point. Starts and stops the channels, the router and the bus, and replays the inbound journal at start.
Supports outbound-only mode (push only) and bidirectional mode (push + receive + agent processing).
Shutdown stops the router, waits (bounded) for the outbound queue it filled, then closes the channels and the bus.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.infra.delivery.notification_ledger import (
    PermanentFailureNotificationLedger,
)
from myrm_agent_harness.infra.delivery.storage import QueuedDelivery

from app.channels.core.bus import MessageBus
from app.channels.core.gateway_instances import ChannelInstancesMixin
from app.channels.core.outbound_media import discard_ephemeral_media
from app.channels.reliability.inbound_journal import (
    InboundJournal,
    restore_inbound,
)
from app.channels.types import (
    ChannelStatus,
    MediaAttachment,
    OutboundMessage,
)
from app.core.infra.background_task import spawn_observed_task

if TYPE_CHECKING:
    from app.channels.media.sticker_vision import (
        StickerVisionService,
    )
    from app.channels.protocols.agent import AgentExecutor
    from app.channels.protocols.background_task import (
        BackgroundTaskHandler,
    )
    from app.channels.protocols.compact import CompactHandler
    from app.channels.protocols.goal_command import (
        GoalCommandHandler,
    )
    from app.channels.protocols.kanban_command import (
        KanbanCommandHandler,
    )
    from app.channels.protocols.learn_command import (
        LearnCommandHandler,
    )
    from app.channels.protocols.locale import LocaleProvider
    from app.channels.protocols.pairing import (
        ChannelPolicyProvider,
        PairingStore,
    )
    from app.channels.protocols.skill_command import (
        SkillCommandHandler,
    )
    from app.channels.protocols.status import StatusProvider
    from app.channels.protocols.topic import TopicManager
    from app.channels.protocols.turn_management import (
        RetryHandler,
        UndoHandler,
    )
    from app.channels.routing.command_defs import CommandDef
    from app.channels.routing.router import AgentRouter
    from app.channels.routing.router_host import (
        PersonalityProvider,
    )
    from app.channels.routing.router_models import (
        ReactionPolicy,
    )
    from app.channels.types import InboundMessage, VoiceConfig

logger = logging.getLogger(__name__)

_SHUTDOWN_OUTBOUND_DRAIN_SECONDS = 5.0


class ChannelGateway(ChannelInstancesMixin):
    """Lifecycle manager for all channel providers.

    Supports two modes:
    - Outbound-only: register channels, publish messages (no AgentRouter)
    - Bidirectional: additionally enable AgentRouter for inbound processing

    Call ``enable_bidirectional`` before ``start`` to activate inbound routing.
    """

    def __init__(
        self,
        dlq_dir: Path | None = None,
        on_permanent_failure: (Callable[[QueuedDelivery, str], Awaitable[None]] | None) = None,
        inbound_journal: InboundJournal | None = None,
        notification_ledger: PermanentFailureNotificationLedger | None = None,
    ) -> None:
        self.bus = MessageBus(
            dlq_dir=dlq_dir,
            on_permanent_failure=on_permanent_failure,
            notification_ledger=notification_ledger,
        )
        self._inbound_journal = inbound_journal
        self._channel_tasks: dict[str, asyncio.Task[None]] = {}
        self._channel_restart_not_before: dict[str, float] = {}
        self._health_task: asyncio.Task[None] | None = None
        self._running = False
        self._router: AgentRouter | None = None
        self._router_restart_attempts = 0
        self._router_restart_not_before = 0.0
        self._dispatch_restart_attempts = 0
        self._dispatch_restart_not_before = 0.0
        self._status_change_callback: Callable[[str, ChannelStatus, ChannelStatus], None] | None = None
        self._groups_change_callback: Callable[[str, list[object]], None] | None = None
        self._connection_change_callback: Callable[[str, bool], None] | None = None

    def enable_bidirectional(
        self,
        pairing_store: PairingStore,
        agent_executor: AgentExecutor,
        policy_provider: ChannelPolicyProvider | None = None,
        voice_config: VoiceConfig | None = None,
        reaction_policy: ReactionPolicy | None = None,
        topic_resolver: TopicManager | None = None,
        compact_handler: CompactHandler | None = None,
        retry_handler: RetryHandler | None = None,
        undo_handler: UndoHandler | None = None,
        personality_provider: PersonalityProvider | None = None,
        sticker_vision: StickerVisionService | None = None,
        extra_commands: tuple[CommandDef, ...] = (),
        skill_command_handler: SkillCommandHandler | None = None,
        goal_handler: GoalCommandHandler | None = None,
        background_handler: BackgroundTaskHandler | None = None,
        kanban_handler: KanbanCommandHandler | None = None,
        learn_handler: LearnCommandHandler | None = None,
        status_provider: StatusProvider | None = None,
        locale_provider: LocaleProvider | None = None,
    ) -> None:
        """Enable bidirectional communication with AgentRouter.

        Must be called before ``start()``.
        compact_handler: Optional handler for /compact command (DB/chat compaction).
        retry_handler: Optional handler for /retry command (re-execute last query).
        undo_handler: Optional handler for /undo command (delete last turn).
        personality_provider: Optional personality template provider for /personality command.
        sticker_vision: Optional sticker vision service for sticker image understanding.
        skill_command_handler: Optional handler for skill-bound slash commands.
        goal_handler: Optional handler for /goal command (persistent cross-turn goals).
        background_handler: Optional handler for /background (/btw /bg) commands.
        kanban_handler: Optional handler for /kanban command (task board management).
        learn_handler: Optional handler for /learn command (directed skill learning).
        status_provider: Optional handler for /status command (session status query).
        """
        from app.channels.routing.router import AgentRouter

        self._router = AgentRouter(
            bus=self.bus,
            pairing_store=pairing_store,
            agent_executor=agent_executor,
            policy_provider=policy_provider,
            voice_config=voice_config,
            reaction_policy=reaction_policy,
            topic_resolver=topic_resolver,
            compact_handler=compact_handler,
            retry_handler=retry_handler,
            undo_handler=undo_handler,
            personality_provider=personality_provider,
            sticker_vision=sticker_vision,
            extra_commands=extra_commands,
            skill_command_handler=skill_command_handler,
            goal_handler=goal_handler,
            background_handler=background_handler,
            kanban_handler=kanban_handler,
            learn_handler=learn_handler,
            status_provider=status_provider,
            locale_provider=locale_provider,
        )
        logger.debug("ChannelGateway: bidirectional mode enabled")

    def set_reaction_policy(self, policy: ReactionPolicy) -> None:
        """Apply a new reaction policy to the running AgentRouter, if enabled."""
        if self._router is not None:
            self._router.set_reaction_policy(policy)

    async def deliver_followup(self, origin: InboundMessage, content: str, media: tuple[MediaAttachment, ...] = ()) -> bool:
        """Say ``content`` with ``media`` in the conversation ``origin`` came from, under the delivery rules of a normal reply.

        Returns True when the reply was sent; False when it was withheld or the router is not enabled.
        """
        if self._router is None:
            discard_ephemeral_media(media)
            return False
        return await self._router.deliver_followup(origin, content, media)

    def is_session_busy(self, origin: InboundMessage) -> bool:
        """Whether the conversation ``origin`` came from is running a turn; False when the router is not enabled."""
        return self._router is not None and self._router.is_session_busy(origin)

    async def publish(self, msg: OutboundMessage) -> None:
        """Publish an outbound message (convenience wrapper)."""
        await self.bus.publish_outbound(msg)

    async def start(self) -> None:
        """Start the Gateway: bus dispatch + all registered channels + optional router."""
        if self._running:
            return
        self._running = True

        await self.bus.start()

        for name, channel in self.bus.channels.items():
            self._channel_tasks[name] = asyncio.create_task(
                self._run_channel(name, channel),
                name=f"channel-{name}",
            )

        if self._router:
            self._router.set_inbound_journal(self._inbound_journal)
            await self._router.start()

        self._health_task = spawn_observed_task(self._health_loop(), name="channel_health")
        logger.info(
            "ChannelGateway started (channels: %s, bidirectional: %s)",
            ", ".join(self.bus.registered_channels) or "none",
            self._router is not None,
        )

        await self._recover_journal()

    async def stop(self) -> None:
        """Stop all channels, router, and the bus."""
        self._running = False

        if self._router:
            await self._router.stop()
        # What the router just published (a delegated task's interruption notice) goes out before the channels close.
        await self.bus.drain_outbound(_SHUTDOWN_OUTBOUND_DRAIN_SECONDS)

        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
            self._health_task = None

        for task in self._channel_tasks.values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._channel_tasks.clear()

        for channel in self.bus.channels.values():
            try:
                await channel.stop()
            except Exception as e:
                logger.warning("Error stopping channel '%s': %s", channel.name, e)

        await self.bus.stop()
        logger.info("ChannelGateway stopped")

    def update_skill_commands(self, commands: tuple[CommandDef, ...]) -> None:
        """Replace all SKILL-type commands in the registry with *commands*.

        Removes existing SKILL commands, then registers the new set.
        Invalid commands (e.g. conflicting with system commands) are skipped
        with a warning to prevent one bad config from breaking all bindings.
        Safe to call at runtime (e.g. when agent command_bindings change).
        No-op if the router is not initialized.
        """
        if not self._router:
            return

        from app.channels.routing.command_defs import (
            CommandKind,
        )

        registry = self._router._registry
        for old_cmd in registry.commands_by_kind(CommandKind.SKILL):
            registry.unregister(old_cmd.name)

        for cmd in commands:
            try:
                registry.register(cmd)
            except ValueError as e:
                logger.warning("Skipped invalid skill command '/%s': %s", cmd.name, e)

    async def _recover_journal(self) -> None:
        """Scan inbound journal for interrupted messages and re-submit them.

        Called once after Gateway.start() completes. Entries that survived a
        crash/restart are rebuilt by ``restore_inbound`` and re-injected into the
        Router via SessionGate; ``metadata.is_recovery=True`` makes the turn keep the
        original entry instead of journaling the message again.
        """
        if not self._inbound_journal or not self._router:
            return

        self._inbound_journal.prune_expired()
        entries = self._inbound_journal.scan_pending()

        if not entries:
            return

        logger.info("InboundJournal: recovering %d interrupted message(s)", len(entries))

        for entry in entries:
            try:
                recovery_msg = restore_inbound(entry)
                self._router._gate.submit(recovery_msg)

                logger.info(
                    "InboundJournal: recovered message for %s/%s",
                    recovery_msg.channel,
                    recovery_msg.chat_id or recovery_msg.sender_id,
                )
            except Exception as e:
                logger.warning("InboundJournal: failed to recover entry %s: %s", entry.id, e)
