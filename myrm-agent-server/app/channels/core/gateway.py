"""Channel Gateway — lifecycle manager for all channel providers.

Manages channel start/stop, health checks with exponential backoff,
error isolation, and optionally the AgentRouter for bidirectional communication.

Health loop:
- Calls ``channel.health_check()`` every ``_HEALTH_CHECK_INTERVAL`` seconds
- Updates ``channel.health`` (ChannelHealth) on success/failure
- Uses exponential backoff with jitter for restart decisions
- Consecutive failures ≥ DEGRADED_THRESHOLD → DEGRADED (warn only)
- DEGRADED/ERROR channels restart when backoff cooldown has elapsed


[INPUT]
- channels.core.bus::MessageBus (POS: async message bus)
- channels.core.base::BaseChannel (POS: channel abstract base class)
- channels.routing.router::AgentRouter (POS: inbound message routing hub)
- channels.routing.command_defs::CommandDef (POS: slash command data model)
- channels.types::ChannelStatus, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)
- channels.protocols.agent::AgentExecutor (POS: agent execution protocol)
- channels.protocols.compact::CompactHandler (POS: /compact business-layer handling protocol)
- channels.protocols.pairing::PairingStore (POS: identity binding protocol)

[OUTPUT]
- ChannelGateway: singleton gateway managing all channel lifecycles

[POS]
Channel system entry point. Manages all channel lifecycles, health checks, and error isolation.
Supports outbound-only mode (push only) and bidirectional mode (push + receive + agent processing).
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.infra.delivery.storage import QueuedDelivery

from app.channels.core.base import BaseChannel
from app.channels.core.bus import MessageBus
from app.channels.reliability.inbound_journal import (
    InboundJournal,
)
from app.channels.types import (
    ChannelCapabilities,
    ChannelIssue,
    ChannelStatus,
    GroupInfo,
    OutboundMessage,
)

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

_HEALTH_CHECK_INTERVAL = 60.0
_BASE_BACKOFF = 5.0
_MAX_BACKOFF = 300.0
_BACKOFF_FACTOR = 2.0
_JITTER_RATIO = 0.25
_DEGRADED_THRESHOLD = 2


class ChannelGateway:
    """Lifecycle manager for all channel providers.

    Supports two modes:
    - Outbound-only: register channels, publish messages (no AgentRouter)
    - Bidirectional: additionally enable AgentRouter for inbound processing

    Call ``enable_bidirectional`` before ``start`` to activate inbound routing.
    """

    def __init__(
        self,
        dlq_dir: Path | None = None,
        on_permanent_failure: (
            Callable[[QueuedDelivery, str], Awaitable[None]] | None
        ) = None,
        inbound_journal: InboundJournal | None = None,
    ) -> None:
        self.bus = MessageBus(
            dlq_dir=dlq_dir, on_permanent_failure=on_permanent_failure
        )
        self._inbound_journal = inbound_journal
        self._channel_tasks: dict[str, asyncio.Task[None]] = {}
        self._health_task: asyncio.Task[None] | None = None
        self._running = False
        self._router: AgentRouter | None = None
        self._status_change_callback: (
            Callable[[str, ChannelStatus, ChannelStatus], None] | None
        ) = None
        self._groups_change_callback: Callable[[str, list[object]], None] | None = None
        self._connection_change_callback: Callable[[str, bool], None] | None = None

    def register(self, channel: BaseChannel) -> None:
        """Register a channel provider and subscribe to its events."""
        self.bus.register_channel(channel)

        channel.on("status_change", self._on_status_change_event)
        channel.on("groups_change", self._on_groups_change_event)
        channel.on("connection_change", self._on_connection_change_event)

    def set_status_change_callback(
        self, callback: Callable[[str, ChannelStatus, ChannelStatus], None]
    ) -> None:
        """Register a callback for channel status changes."""
        self._status_change_callback = callback

    def set_groups_change_callback(
        self, callback: Callable[[str, list[object]], None]
    ) -> None:
        """Register a callback for groups list changes."""
        self._groups_change_callback = callback

    def set_connection_change_callback(
        self, callback: Callable[[str, bool], None]
    ) -> None:
        """Register a callback for channel connection state changes."""
        self._connection_change_callback = callback

    def _on_status_change_event(self, channel_name: str, data: object) -> None:
        """Handle status_change event from channel."""
        if not isinstance(data, dict):
            return
        old_status = data.get("old_status")
        new_status = data.get("new_status")

        if not isinstance(old_status, ChannelStatus) or not isinstance(
            new_status, ChannelStatus
        ):
            return

        logger.info(
            "ChannelGateway: %s status changed %s -> %s",
            channel_name,
            old_status.value,
            new_status.value,
        )
        if self._status_change_callback:
            self._status_change_callback(channel_name, old_status, new_status)

    def _on_connection_change_event(self, channel_name: str, data: object) -> None:
        """Handle connection_change event from channel."""
        if not isinstance(data, dict):
            return
        connected = bool(data.get("connected", False))
        logger.info(
            "ChannelGateway: %s connection_change -> %s", channel_name, connected
        )
        if self._connection_change_callback:
            self._connection_change_callback(channel_name, connected)

    def _on_groups_change_event(self, channel_name: str, data: object) -> None:
        """Handle groups_change event from channel."""
        if not isinstance(data, list):
            return
        logger.info(
            "ChannelGateway: %s groups updated (%d groups)", channel_name, len(data)
        )
        if self._groups_change_callback:
            self._groups_change_callback(channel_name, data)

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
        status_provider: StatusProvider | None = None,
        locale_provider: LocaleProvider | None = None,
        admin_checker: Callable[[InboundMessage], bool] | None = None,
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
            status_provider=status_provider,
            locale_provider=locale_provider,
            admin_checker=admin_checker,
        )
        logger.debug("ChannelGateway: bidirectional mode enabled")

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

        self._health_task = asyncio.create_task(self._health_loop())
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

    async def disable_channel(self, name: str) -> bool:
        """Disable a channel at runtime (stop it and set DISABLED status).

        Returns True if the channel was found and disabled.
        """
        channel = self.bus.channels.get(name)
        if not channel:
            return False
        if channel.status == ChannelStatus.DISABLED:
            return True

        task = self._channel_tasks.pop(name, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        try:
            await channel.stop()
        except Exception:
            pass

        channel._status = ChannelStatus.DISABLED
        logger.info("Channel '%s' disabled", name)
        return True

    async def enable_channel(self, name: str) -> bool:
        """Re-enable a previously disabled channel.

        Returns True if the channel was found and re-enabled.
        """
        channel = self.bus.channels.get(name)
        if not channel:
            return False
        if channel.status != ChannelStatus.DISABLED:
            return True

        channel._status = ChannelStatus.IDLE
        self._channel_tasks[name] = asyncio.create_task(
            self._run_channel(name, channel),
            name=f"channel-{name}",
        )
        logger.info("Channel '%s' enabled", name)
        return True

    _MAX_INSTANCES_PER_TYPE = 5

    @staticmethod
    def _resolve_channel_type(channel: BaseChannel) -> str:
        """Extract the base channel type from the formal ``channel_type`` attribute."""
        return channel.channel_type or channel.__class__.name

    def _count_instances(self, channel_type: str) -> int:
        """Count existing instances (including the default) for a channel type."""
        return sum(
            1
            for n, ch in self.bus.channels.items()
            if self._resolve_channel_type(ch) == channel_type
        )

    async def add_channel(self, channel: BaseChannel) -> str:
        """Hot-add a channel instance at runtime.

        Registers the channel in the bus, starts it, and begins health monitoring.
        Raises ValueError if the per-type instance limit is exceeded.
        Returns the channel name.
        """
        if not self._running:
            raise RuntimeError("Gateway not running; call start() first")

        channel_type = self._resolve_channel_type(channel)
        existing_count = self._count_instances(channel_type)
        if existing_count >= self._MAX_INSTANCES_PER_TYPE:
            raise ValueError(
                f"Instance limit reached: max {self._MAX_INSTANCES_PER_TYPE} "
                f"instances for channel type '{channel_type}'"
            )

        self.bus.register_channel(channel)
        channel.on("status_change", self._on_status_change_event)
        channel.on("groups_change", self._on_groups_change_event)
        channel.on("connection_change", self._on_connection_change_event)

        self._channel_tasks[channel.name] = asyncio.create_task(
            self._run_channel(channel.name, channel),
            name=f"channel-{channel.name}",
        )
        logger.info("Channel '%s' hot-added", channel.name)
        return channel.name

    async def remove_channel(self, name: str) -> bool:
        """Hot-remove a channel instance at runtime.

        Stops the channel, cancels its task, and unregisters from the bus.
        Returns True if the channel was found and removed.
        """
        channel = self.bus.channels.get(name)
        if not channel:
            return False

        task = self._channel_tasks.pop(name, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        try:
            await channel.stop()
        except Exception as e:
            logger.warning("Error stopping channel '%s' during removal: %s", name, e)

        channel.clear_listeners()
        self.bus.unregister_channel(name)
        logger.info("Channel '%s' hot-removed", name)
        return True

    def list_instances(self, channel_type: str) -> list[str]:
        """List all instance names for a given channel type."""
        return [
            n
            for n, ch in self.bus.channels.items()
            if self._resolve_channel_type(ch) == channel_type
        ]

    def get_channel_capabilities(self, channel_name: str) -> ChannelCapabilities | None:
        """Get the declared capabilities of a registered channel."""
        channel = self.bus.get_channel(channel_name)
        return channel.capabilities if channel else None

    def get_status(self) -> dict[str, ChannelStatus]:
        """Get status of all registered channels."""
        return {name: channel.status for name, channel in self.bus.channels.items()}

    def collect_all_issues(self) -> dict[str, list[ChannelIssue]]:
        """Collect structured diagnostic issues from all registered channels."""
        result: dict[str, list[ChannelIssue]] = {}
        for name, channel in self.bus.channels.items():
            issues = channel.collect_issues()
            if issues:
                result[name] = issues
        return result

    async def get_health_summary(
        self,
        *,
        timeout: float = 5.0,
    ) -> dict[str, dict[str, object]]:
        """Aggregate health status from all channels concurrently.

        Args:
            timeout: Per-channel health_check timeout in seconds.

        Returns a dict keyed by channel name with health, status, and issues.
        """

        async def _check(name: str, ch: BaseChannel) -> tuple[str, dict[str, object]]:
            try:
                healthy = await asyncio.wait_for(ch.health_check(), timeout=timeout)
            except Exception:
                healthy = False
            issues = ch.collect_issues()
            return name, {
                "status": ch.status.value,
                "healthy": healthy,
                "consecutive_failures": ch.health.consecutive_failures,
                "circuit_open": ch.health.circuit_open,
                "last_error": ch.health.last_error,
                "delivery_success_rate": ch.activity.delivery_success_rate,
                "issues": [
                    {
                        "kind": i.kind.value,
                        "severity": i.severity.value,
                        "message": i.message,
                    }
                    for i in issues
                ],
            }

        results = await asyncio.gather(
            *[_check(n, ch) for n, ch in self.bus.channels.items()]
        )
        return dict(results)

    async def reload_channel(self, name: str) -> bool:
        """Hot-reload a channel: stop the old instance and restart it.

        Returns True if the channel was found and reloaded.
        """
        channel = self.bus.channels.get(name)
        if not channel:
            return False

        task = self._channel_tasks.pop(name, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        try:
            await channel.stop()
        except Exception:
            logger.warning(
                "Channel '%s': error during reload stop", name, exc_info=True
            )

        channel._status = ChannelStatus.IDLE
        self._channel_tasks[name] = asyncio.create_task(
            self._run_channel(name, channel),
            name=f"channel-{name}",
        )
        logger.info("Channel '%s' reloaded", name)
        return True

    async def list_channel_groups(
        self, *, force_refresh: bool = False
    ) -> list[GroupInfo]:
        """Aggregate group lists from all channels concurrently.

        Each provider's ``list_groups`` should set ``GroupInfo.channel``, but this
        method acts as a safety net: any ``GroupInfo`` with an empty ``channel``
        field is patched with the provider's registered name.

        Uses ``asyncio.gather`` for concurrent fetching — total latency equals
        the slowest channel rather than the sum of all channels.
        """
        group_channels: list[tuple[str, BaseChannel]] = [
            (name, ch)
            for name, ch in self.bus.channels.items()
            if hasattr(ch, "list_groups")
        ]
        if not group_channels:
            return []

        async def _fetch(name: str, channel: BaseChannel) -> list[GroupInfo]:
            try:
                return await channel.list_groups(force_refresh=force_refresh)
            except Exception:
                logger.warning(
                    "Failed to list groups for channel '%s'", name, exc_info=True
                )
                return []

        results = await asyncio.gather(*[_fetch(n, ch) for n, ch in group_channels])

        all_groups: list[GroupInfo] = []
        for (name, _), groups in zip(group_channels, results, strict=True):
            for g in groups:
                if not g.channel:
                    from dataclasses import replace

                    g = replace(g, channel=name)
                all_groups.append(g)
        return all_groups

    async def _run_channel(self, name: str, channel: BaseChannel) -> None:
        """Run a single channel with error isolation."""
        if channel.status == ChannelStatus.DISABLED:
            logger.debug("Channel '%s' registered as disabled, skipping start", name)
            return
        if not channel.should_auto_start():
            logger.debug("Channel '%s' on-demand, staying idle", name)
            return
        try:
            await channel.start()
            if channel.status == ChannelStatus.RUNNING:
                logger.info("Channel '%s' started", name)
            else:
                logger.debug("Channel '%s' idle (not configured)", name)
        except Exception as e:
            logger.warning("Channel '%s' failed to start: %s", name, e)
            channel._status = ChannelStatus.ERROR

    async def _health_loop(self) -> None:
        """Periodic health check with exponential backoff restart."""
        while self._running:
            try:
                await asyncio.sleep(_HEALTH_CHECK_INTERVAL)
            except asyncio.CancelledError:
                break

            for name, channel in self.bus.channels.items():
                if channel.status in (ChannelStatus.STOPPED, ChannelStatus.DISABLED):
                    continue

                try:
                    healthy = await channel.health_check()
                except Exception as exc:
                    healthy = False
                    logger.warning("Health check exception for '%s': %s", name, exc)

                if healthy:
                    if channel.health.consecutive_failures > 0:
                        logger.warning(
                            "Channel '%s' recovered after %d failures",
                            name,
                            channel.health.consecutive_failures,
                        )
                    channel.health.record_success()
                    if channel.status == ChannelStatus.DEGRADED:
                        channel._status = ChannelStatus.RUNNING
                    continue

                channel.health.record_failure()

                failures = channel.health.consecutive_failures
                if (
                    failures >= _DEGRADED_THRESHOLD
                    and channel.status == ChannelStatus.RUNNING
                ):
                    channel._status = ChannelStatus.DEGRADED
                    logger.warning(
                        "Channel '%s' degraded (%d consecutive failures)",
                        name,
                        failures,
                    )

                if self._should_restart(channel):
                    logger.warning(
                        "Channel '%s' restarting (failures=%d, backoff=%.1fs)",
                        name,
                        failures,
                        self._compute_backoff(failures),
                    )
                    await self._restart_channel(name, channel)

    @staticmethod
    def _compute_backoff(failures: int) -> float:
        base = min(_BASE_BACKOFF * (_BACKOFF_FACTOR ** (failures - 1)), _MAX_BACKOFF)
        jitter = base * _JITTER_RATIO * (2 * random.random() - 1)
        return base + jitter

    @staticmethod
    def _should_restart(channel: BaseChannel) -> bool:
        """Decide whether enough time has elapsed since the last failure to retry."""
        h = channel.health
        if h.consecutive_failures < _DEGRADED_THRESHOLD:
            return False
        if h.last_failure_at is None:
            return True
        backoff = min(
            _BASE_BACKOFF * (_BACKOFF_FACTOR ** (h.consecutive_failures - 1)),
            _MAX_BACKOFF,
        )
        return (time.monotonic() - h.last_failure_at) >= backoff

    async def _restart_channel(self, name: str, channel: BaseChannel) -> None:
        """Restart a failed channel."""
        try:
            await channel.stop()
        except Exception:
            pass

        old_task = self._channel_tasks.get(name)
        if old_task and not old_task.done():
            old_task.cancel()
            try:
                await old_task
            except asyncio.CancelledError:
                pass

        self._channel_tasks[name] = asyncio.create_task(
            self._run_channel(name, channel),
            name=f"channel-{name}",
        )

    async def _recover_journal(self) -> None:
        """Scan inbound journal for interrupted messages and re-submit them.

        Called once after Gateway.start() completes. Entries that survived a
        crash/restart are re-injected into the Router via SessionGate with
        ``metadata.is_recovery=True`` so agents can handle idempotency.
        """
        if not self._inbound_journal or not self._router:
            return

        self._inbound_journal.prune_expired()
        entries = self._inbound_journal.scan_pending()

        if not entries:
            return

        import json

        from app.channels.types import InboundMessage

        logger.info(
            "InboundJournal: recovering %d interrupted message(s)", len(entries)
        )

        for entry in entries:
            try:
                metadata = (
                    json.loads(entry.metadata_json) if entry.metadata_json else {}
                )
                metadata["is_recovery"] = True
                metadata["recovery_entry_id"] = entry.id

                recovery_msg = InboundMessage(
                    channel=entry.channel,
                    sender_id=entry.sender_id,
                    content=entry.content,
                    chat_id=entry.chat_id,
                    user_id=entry.user_id,
                    is_group=entry.is_group,
                    metadata=metadata,
                    thread_id=entry.thread_id,
                )

                self._router._gate.submit(recovery_msg)

                logger.info(
                    "InboundJournal: recovered message for %s/%s",
                    entry.channel,
                    entry.chat_id,
                )
            except Exception as e:
                logger.warning(
                    "InboundJournal: failed to recover entry %s: %s", entry.id, e
                )
