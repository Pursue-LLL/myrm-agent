"""Agent router — routes inbound channel messages to Agent execution.

Consumes InboundMessage from the MessageBus, applies DM/group policy,
resolves the sender's identity, executes the Agent via AgentExecutor,
and publishes the result as an OutboundMessage.

Supports slash commands (/stop, /new, /compact, /retry, /undo, /bind, /unbind, /topic, /goal, /steer, /queue)
and voice STT/TTS via voice_handler module.


[INPUT]
- channels.core.bus::MessageBus (POS: async message bus)
- channels.routing.command_defs::CommandAction, CommandKind (POS: slash command data model and enums)
- channels.routing.command_registry::CommandRegistry, ResolvedCommand (POS: central O(1) command lookup)
- channels.routing.commands::parse_approval_command, handle_* (POS: slash command argument parsing and handling)
- channels.routing.policy_resolver::PolicyResolver (POS: DM/group policy resolution + identity resolution)
- channels.routing.session_gate::SessionGate (POS: message debounce and concurrency control)
- channels.routing.context_buffer::GroupContextBuffer (POS: group chat context accumulation buffer)
- channels.routing.message_effects::MessageEffects (POS: typing/reaction/placeholder side effects)
- channels.routing.router_commands::RouterCommandsMixin (POS: /stop, approval, and topic command handling)
- channels.routing.router_execution::RouterExecutionMixin (POS: execution lifecycle — prepare/effects/stream/deliver/cleanup)
- channels.routing.router_constants::limits (POS: concurrency, dedup, throttle, cleanup TTL)
- channels.routing.router_host::RouterStreamHost, (POS: Typing protocols: host instance attributes required by Router Mixins.)
  RouterExecutionHost (POS: typing.Protocol for mixin host attributes)
- channels.routing.router_models::_RouterExecutionContext etc. (POS: internal data classes)
- channels.routing.router_stream::RouterStreamMixin (POS: execute_stream consumption and placeholder throttled editing)
- channels.routing.router_stream_throttle::should_skip_throttled_placeholder_edit (POS: placeholder edit interval pure function)
- channels.routing.router_keys::routing_session_key (POS: channel+peer mapping key format)
- channels.protocols.agent::AgentExecutor (POS: agent execution protocol)
- channels.protocols.compact::CompactHandler (POS: /compact business-layer handling protocol)
- channels.protocols.goal_command::GoalCommandHandler (POS: business-layer handler protocol for /goal slash commands)
- channels.protocols.skill_command::SkillCommandHandler (POS: business-layer handler for skill-bound slash commands)
- channels.protocols.turn_management::RetryHandler, UndoHandler (POS: /retry, /undo protocols)
- channels.protocols.pairing::PairingStore, ChannelPolicyProvider (POS: identity binding and policy protocols)
- channels.protocols.topic::TopicManager (POS: topic management protocol)
- channels.types::InboundMessage, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)
- channels.voice.handler::transcribe_inbound, has_audio_attachment (POS: voice processing)
- channels.media.image_enrichment::enrich_image_inbound, has_image_attachment (POS: image attachment base64 enrichment)
- channels.media.video_enrichment::enrich_video_inbound, has_video_attachment (POS: video attachment metadata enrichment)

[OUTPUT]
- AgentRouter: inbound message routing hub managing dedup, command dispatch, agent task lifecycle, and streaming progress
- _ActiveTask, _CleanupEntry, _RouterExecutionContext, _AgentTurnScratch: see `router_models.py`
- Concurrency and dedup constants: see `router_constants.py`

[POS]
Core inbound message routing loop. Connects MessageBus (inbound queue) to agent executor.
Uses PolicyResolver to check DM/group policies and resolve user identity;
group policies may rewrite InboundMessage (prefix stripping, context_messages, etc.),
with the rewritten message stored in `_RouterExecutionContext.exec_msg`. After successful
`prepare`, `_execute_prepared_context` handles active task registration, side effects,
streaming execution, and result delivery.
`SessionGate.on_task_complete` uses the `msg` from the current `_handle_merged` scope
(a new `replace` instance after voice transcription); `SessionGate` releases pending
by `gate_key(msg)` regardless of object identity, and STT does not change channel/peer
fields so the key matches the merged message.
Slash commands are handled via the commands module, completing the bidirectional conversation loop.
Manages active task mapping, approval message IDs, and cleanup janitor。
`RouterExecutionMixin` / `RouterStreamMixin` / `RouterCommandsMixin`  Method
Uses Protocol constraints from `router_host` for `self` required attributes。
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.channels.routing.router_host import (
        PersonalityProvider,
    )
    from app.channels.types import InboundMessage

from myrm_agent_harness.utils.locale import resolve_locale

from app.channels.core.bus import (
    MessageBus,
    set_correlation_context,
)
from app.channels.i18n import get_text, resolve_message_locale
from app.channels.media.image_enrichment import (
    enrich_image_inbound,
)
from app.channels.media.image_enrichment import (
    has_image_attachment as has_image_attachment_fn,
)
from app.channels.media.sticker_vision import (
    StickerVisionService,
    describe_sticker_inbound,
)
from app.channels.media.video_enrichment import (
    enrich_video_inbound,
)
from app.channels.media.video_enrichment import (
    has_video_attachment as has_video_attachment_fn,
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
from app.channels.reliability.inbound_journal import (
    InboundJournal,
)
from app.channels.routing.command_defs import (
    CommandAction,
    CommandDef,
    CommandKind,
)
from app.channels.routing.command_registry import (
    CommandRegistry,
    ResolvedCommand,
)
from app.channels.routing.commands import (
    is_explicit_approval_command,
    parse_approval_command,
    parse_personality_args,
    parse_topic_args,
    parse_yolo_args,
)
from app.channels.routing.context_buffer import (
    GroupContextBuffer,
)
from app.channels.routing.graceful_degradation import (
    GracefulDegradationController,
)
from app.channels.routing.message_effects import MessageEffects
from app.channels.routing.policy_resolver import PolicyResolver
from app.channels.routing.retry_policy import (
    RetryConfig as RouterRetryConfig,
)
from app.channels.routing.retry_policy import (
    RetryPolicy,
)
from app.channels.routing.router_commands import (
    RouterCommandsMixin,
)
from app.channels.routing.router_constants import (
    _CLEANUP_TTL,
    _DEDUP_MAX_SIZE,
    _DEDUP_TTL,
    _MAX_CONCURRENT_AGENTS,
)
from app.channels.routing.router_execution import (
    RouterExecutionMixin,
)
from app.channels.routing.router_models import (
    ReactionPolicy,
    _ActiveTask,
    _AgentTurnScratch,
    _CleanupEntry,
)
from app.channels.routing.router_stream import RouterStreamMixin
from app.channels.routing.session_gate import (
    SessionGate,
    SessionGateConfig,
)
from app.channels.routing.session_rate_limiter import (
    SessionRateLimiter,
)
from app.channels.routing.stream_config import StreamConfig
from app.channels.routing.stream_manager import (
    AdaptiveThrottler,
    BlockChunker,
    ChunkConfig,
    IncrementalEditor,
    ProgressEstimator,
    StreamCoordinator,
)
from app.channels.routing.stream_metrics import StreamMetrics
from app.channels.types import (
    InboundMessage,
    OutboundMessage,
    VoiceConfig,
)
from app.channels.voice.handler import (
    has_audio_attachment,
    transcribe_inbound,
)

logger = logging.getLogger(__name__)


class AgentRouter(RouterExecutionMixin, RouterStreamMixin, RouterCommandsMixin):
    """Routes inbound messages through policy check, identity resolution, and Agent execution.

    Lifecycle:
    1. Consume InboundMessage from MessageBus._inbound
    2. Branch: group → GroupPolicy + mention gate; DM → DmPolicy + PairingStore
    3. Resolve sender → system user_id
    4. Execute Agent via AgentExecutor
    5. Publish OutboundMessage back to MessageBus._outbound
    """

    def __init__(
        self,
        bus: MessageBus,
        pairing_store: PairingStore,
        agent_executor: AgentExecutor,
        policy_provider: ChannelPolicyProvider | None = None,
        voice_config: VoiceConfig | None = None,
        reaction_policy: ReactionPolicy | None = None,
        topic_resolver: TopicManager | None = None,
        session_gate_config: SessionGateConfig | None = None,
        compact_handler: CompactHandler | None = None,
        retry_handler: RetryHandler | None = None,
        undo_handler: UndoHandler | None = None,
        stream_config: StreamConfig | None = None,
        personality_provider: PersonalityProvider | None = None,
        sticker_vision: StickerVisionService | None = None,
        skill_command_handler: SkillCommandHandler | None = None,
        goal_handler: GoalCommandHandler | None = None,
        background_handler: BackgroundTaskHandler | None = None,
        status_provider: StatusProvider | None = None,
        extra_commands: tuple[CommandDef, ...] = (),
        admin_checker: Callable[[InboundMessage], bool] | None = None,
        locale_provider: LocaleProvider | None = None,
        approval_co_approvers: frozenset[str] | None = None,
    ) -> None:
        self._bus = bus
        self._executor = agent_executor
        self._compact_handler = compact_handler
        self._retry_handler = retry_handler
        self._undo_handler = undo_handler
        self._voice = voice_config
        self._sticker_vision = sticker_vision
        self._skill_command_handler = skill_command_handler
        self._goal_handler = goal_handler
        self._background_handler = background_handler
        self._status_provider = status_provider
        self._reaction_policy = reaction_policy or ReactionPolicy()
        self._topic_resolver = topic_resolver

        self._registry = CommandRegistry()
        for cmd in extra_commands:
            try:
                self._registry.register(cmd)
            except ValueError as e:
                logger.warning("Skipped invalid extra command '/%s': %s", cmd.name, e)
        self._fx = MessageEffects(bus)
        self._resolver = PolicyResolver(
            pairing=pairing_store,
            policy=policy_provider,
            context_buffer=GroupContextBuffer(),
            fx=self._fx,
            get_channel=bus.get_channel,
        )
        self._semaphore = asyncio.Semaphore(_MAX_CONCURRENT_AGENTS)
        self._gate = SessionGate(
            session_gate_config or SessionGateConfig(),
            on_ready=self._handle_merged,
        )
        self._task: asyncio.Task[None] | None = None
        self._active_tasks: dict[str, _ActiveTask] = {}
        self._cleanups: dict[str, _CleanupEntry] = {}
        self._approval_msg_ids: dict[str, str] = {}
        self._approval_co_approvers: frozenset[str] = approval_co_approvers or frozenset()
        self._janitor_task: asyncio.Task[None] | None = None
        self._seen_messages: dict[str, float] = {}
        self._new_session_peers: dict[str, float] = {}
        self._session_yolo: dict[str, tuple[float, int | None]] = {}
        self._session_personality: dict[str, str] = {}
        self._personality_provider = personality_provider
        self._running = False
        self._stream_metrics = StreamMetrics()
        self._admin_checker = admin_checker
        self._locale_provider = locale_provider

        stream_config = stream_config or StreamConfig()
        self._session_rate_limiter = SessionRateLimiter(max_updates_per_minute=60)
        self._degradation_controller = GracefulDegradationController(
            failure_threshold=3,
            success_threshold=2,
            max_level=4,
        )

        self._progress_estimator = ProgressEstimator(
            session_ttl_seconds=stream_config.progress_session_ttl_seconds
        )

        chunker = BlockChunker(
            ChunkConfig(
                block_size=stream_config.block_size,
                enable_code_fence_protection=stream_config.enable_code_fence_protection,
                prefer_newline_breaks=stream_config.prefer_newline_breaks,
            )
        )
        editor = IncrementalEditor()
        throttler = AdaptiveThrottler()
        self._stream_coordinator = StreamCoordinator(
            chunker,
            editor,
            throttler,
            self._degradation_controller,
            session_ttl_seconds=stream_config.coordinator_session_ttl_seconds,
        )

        self._retry_policy = RetryPolicy(
            RouterRetryConfig(
                max_retries=3,
                base_delay=0.5,
                backoff_multiplier=2.0,
                ui_feedback=True,
            )
        )
        self._inbound_journal: InboundJournal | None = None

    def set_inbound_journal(self, journal: InboundJournal | None) -> None:
        """Inject inbound journal for crash recovery. Called by Gateway before start."""
        self._inbound_journal = journal

    async def start(self) -> None:
        """Start the inbound message consumption loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._consume_loop())
        self._start_janitor()
        logger.info("AgentRouter started (max_concurrent=%d)", _MAX_CONCURRENT_AGENTS)

    async def stop(self) -> None:
        """Stop the consumption loop and cancel all in-flight agent tasks."""
        self._running = False

        for entry in self._active_tasks.values():
            entry.cancel_token.cancel("Router stopping")
            if not entry.task.done():
                entry.task.cancel()

        self._active_tasks.clear()
        self._cleanups.clear()
        self._approval_msg_ids.clear()

        await self._stop_janitor()

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        self._seen_messages.clear()
        self._gate.clear()
        logger.info("AgentRouter stopped")

    def _start_janitor(self) -> None:
        if self._janitor_task is None or self._janitor_task.done():
            self._janitor_task = asyncio.create_task(self._janitor_loop())

    async def _stop_janitor(self) -> None:
        if self._janitor_task and not self._janitor_task.done():
            self._janitor_task.cancel()
            try:
                await self._janitor_task
            except asyncio.CancelledError:
                pass

    async def _janitor_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            now = time.monotonic()
            expired_keys = [
                key
                for key, entry in self._cleanups.items()
                if now - entry.created_at > _CLEANUP_TTL
            ]
            for key in expired_keys:
                entry = self._cleanups.pop(key, None)
                if entry:
                    try:
                        await entry.cleanup()
                    except Exception as e:
                        logger.warning("[JANITOR] Cleanup failed for %s: %s", key, e)
            if expired_keys:
                logger.info(
                    "[JANITOR] Cleaned up %d expired callbacks", len(expired_keys)
                )

            coordinator_cleaned = self._stream_coordinator.cleanup_expired_sessions()
            estimator_cleaned = self._progress_estimator.cleanup_expired_sessions()
            if coordinator_cleaned > 0 or estimator_cleaned > 0:
                logger.info(
                    "[JANITOR] Streaming TTL cleanup: coordinator=%d, estimator=%d",
                    coordinator_cleaned,
                    estimator_cleaned,
                )

    async def _consume_loop(self) -> None:
        """Continuously consume inbound messages and dispatch via SessionGate.

        Uses CommandRegistry.resolve() for O(1) slash command dispatch instead
        of a linear if-elif chain. Approval commands are still checked first
        because they include non-slash shortcuts (1, y, yes, etc.).
        """
        while self._running:
            try:
                msg = await asyncio.wait_for(self._bus.consume_inbound(), timeout=1.0)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            if self._is_duplicate(msg):
                logger.debug(
                    "Duplicate message %s from %s, skipping",
                    msg.message_id,
                    msg.channel,
                )
                continue

            msg = await self._enrich_message_locale(msg)

            is_reaction = bool(msg.metadata.get("reaction"))
            if is_reaction:
                approval_cmd = parse_approval_command(msg.content)
                if (
                    approval_cmd is not None
                    and self._is_reaction_approval_valid(msg)
                ):
                    asyncio.create_task(
                        self._handle_approval_command(msg, approval_cmd)
                    )
                continue

            approval_cmd = parse_approval_command(msg.content)
            if approval_cmd is not None:
                if is_explicit_approval_command(
                    msg.content
                ) or self._has_pending_approval(msg):
                    asyncio.create_task(
                        self._handle_approval_command(msg, approval_cmd)
                    )
                    continue

            resolved = self._registry.resolve(msg.content)
            if resolved is not None:
                handled = await self._dispatch_resolved(msg, resolved)
                if handled:
                    continue

            self._gate.submit(msg)

    async def _enrich_message_locale(self, msg: InboundMessage) -> InboundMessage:
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

    def _check_admin_permission(self, msg: InboundMessage) -> bool:
        """Check if the sender has admin permission for restricted commands.

        Uses the admin_checker callback if provided; defaults to allowing all.
        In DMs the sender is always the owner. In groups, the server layer
        determines admin status via the callback.
        """
        if self._admin_checker is None:
            return True
        return self._admin_checker(msg)

    async def _dispatch_resolved(
        self,
        msg: InboundMessage,
        resolved: ResolvedCommand,
    ) -> bool:
        """Dispatch a resolved command to its handler. Returns True if consumed."""
        cmd = resolved.command_def
        action = cmd.action

        if cmd.requires_admin and not self._check_admin_permission(msg):
            chat_id = msg.chat_id or msg.sender_id
            reply = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=get_text(msg, "permission_denied", cmd=cmd.name),
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=(
                    (msg.message_id or str(msg.metadata.get("message_id", "")))
                    if msg.is_group
                    else None
                ),
            )
            asyncio.create_task(self._bus.publish_outbound(reply))
            return True

        if cmd.kind == CommandKind.SYSTEM and action is not None:
            return await self._dispatch_system_command(msg, action, resolved.raw_args)

        if cmd.kind == CommandKind.AGENT_ROUTE:
            self._gate.submit(msg)
            return True

        if cmd.kind == CommandKind.SKILL:
            asyncio.create_task(self._handle_skill_command(msg, cmd, resolved.raw_args))
            return True

        return False

    async def _dispatch_system_command(
        self,
        msg: InboundMessage,
        action: CommandAction,
        raw_args: str,
    ) -> bool:
        """Dispatch a system command by action type. Returns True if consumed."""
        if action == CommandAction.STOP:
            asyncio.create_task(self._cancel_active_task(msg))
            return True

        if action == CommandAction.NEW_SESSION:
            asyncio.create_task(self._handle_new_session(msg))
            return True

        if action == CommandAction.COMPACT:
            asyncio.create_task(self._handle_compact(msg, raw_args))
            return True

        if action == CommandAction.RETRY:
            asyncio.create_task(self._handle_retry(msg))
            return True

        if action == CommandAction.UNDO:
            asyncio.create_task(self._handle_undo(msg))
            return True

        if action == CommandAction.YOLO:
            parsed = parse_yolo_args(raw_args)
            if parsed:
                asyncio.create_task(self._handle_yolo_command(msg, parsed))
            else:
                chat_id = msg.chat_id or msg.sender_id
                reply = OutboundMessage(
                    channel=msg.channel,
                    recipient_id=chat_id,
                    content=get_text(msg, "yolo_invalid_usage"),
                    user_id=msg.user_id or "",
                    thread_id=msg.thread_id,
                    reply_to_id=(
                        (msg.message_id or str(msg.metadata.get("message_id", "")))
                        if msg.is_group
                        else None
                    ),
                )
                asyncio.create_task(self._bus.publish_outbound(reply))
            return True

        if action == CommandAction.PERSONALITY:
            style = parse_personality_args(raw_args)
            asyncio.create_task(self._handle_personality_command(msg, style))
            return True

        if action in (CommandAction.BIND, CommandAction.UNBIND, CommandAction.TOPIC):
            action_name = action.value
            topic_cmd = parse_topic_args(action_name, raw_args)
            asyncio.create_task(self._handle_topic_command(msg, topic_cmd))
            return True

        if action == CommandAction.GOAL:
            asyncio.create_task(self._handle_goal_command(msg, raw_args))
            return True

        if action == CommandAction.SUBGOAL:
            asyncio.create_task(self._handle_subgoal_command(msg, raw_args))
            return True

        if action == CommandAction.STEER:
            asyncio.create_task(self._handle_steer_command(msg, raw_args))
            return True

        if action == CommandAction.QUEUE:
            asyncio.create_task(self._handle_queue_command(msg, raw_args))
            return True

        if action == CommandAction.BACKGROUND:
            asyncio.create_task(self._handle_background_command(msg, raw_args))
            return True

        if action == CommandAction.HANDOFF:
            asyncio.create_task(self._handle_handoff_command(msg, raw_args))
            return True

        if action == CommandAction.STATUS:
            asyncio.create_task(self._handle_status_command(msg))
            return True

        if action == CommandAction.HELP:
            asyncio.create_task(self._handle_help_command(msg))
            return True

        return False

    async def _handle_skill_command(
        self,
        msg: InboundMessage,
        cmd: CommandDef,
        raw_args: str,
    ) -> None:
        """Handle a skill-bound slash command."""
        chat_id = msg.chat_id or msg.sender_id

        if not self._skill_command_handler or not cmd.skill_id:
            reply = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=get_text(msg, "skill_not_configured", cmd=cmd.name),
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=(
                    (msg.message_id or str(msg.metadata.get("message_id", "")))
                    if msg.is_group
                    else None
                ),
            )
            await self._bus.publish_outbound(reply)
            return

        skill_msg = await self._skill_command_handler(msg, cmd.skill_id, raw_args)
        if skill_msg is None:
            reply = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=get_text(msg, "skill_load_failed", cmd=cmd.name),
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=(
                    (msg.message_id or str(msg.metadata.get("message_id", "")))
                    if msg.is_group
                    else None
                ),
            )
            await self._bus.publish_outbound(reply)
            return

        self._gate.submit(skill_msg)

    async def _handle_help_command(self, msg: InboundMessage) -> None:
        """Handle /help command: show available commands."""
        chat_id = msg.chat_id or msg.sender_id
        locale = resolve_message_locale(msg)
        lines = self._registry.help_lines(locale)
        content = get_text(msg, "help_header") + "\n" + "\n".join(lines)
        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=chat_id,
            content=content,
            user_id=msg.user_id or "",
            thread_id=msg.thread_id,
            reply_to_id=(
                (msg.message_id or str(msg.metadata.get("message_id", "")))
                if msg.is_group
                else None
            ),
        )
        await self._bus.publish_outbound(reply)

    def _is_duplicate(self, msg: InboundMessage) -> bool:
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
            self._seen_messages = {
                k: v for k, v in self._seen_messages.items() if v > cutoff
            }

        return False

    async def _handle_merged(self, msg: InboundMessage) -> None:
        """Process a (possibly merged) inbound message with concurrency control.

        Called by SessionGate after debounce timer expires or pending queue drains.
        Gate notification (on_task_complete) is in the outermost finally to
        guarantee drain regardless of early return, exception, or cancellation.

        ``exec_for_error`` is the InboundMessage passed to ``send_error_reply`` and
        used for ``channel`` on the outer ``cleanup_placeholder`` path: it matches
        ``msg`` after ``transcribe_inbound`` (when voice ran), and ``ctx.exec_msg``
        after ``_prepare_execution_context`` succeeds. Successful ``prepare`` hands
        off to ``_execute_prepared_context`` (active task registration, stream, delivery).
        """
        journal_entry_id: str | None = None
        if self._inbound_journal and not msg.metadata.get("is_recovery"):
            from app.channels.reliability.inbound_journal import (
                create_journal_entry_from_inbound,
            )

            entry = create_journal_entry_from_inbound(msg)
            self._inbound_journal.write(entry)
            journal_entry_id = entry.id
        elif self._inbound_journal and msg.metadata.get("recovery_entry_id"):
            journal_entry_id = str(msg.metadata["recovery_entry_id"])

        channel_instance = self._bus.get_channel(msg.channel)
        if channel_instance and msg.channel_capabilities is None:
            msg = dataclasses.replace(
                msg, channel_capabilities=channel_instance.capabilities
            )

        from app.channels.routing.router_keys import (
            routing_session_key,
        )

        chat_id_for_key = msg.chat_id or msg.sender_id
        session_key = routing_session_key(msg.channel, chat_id_for_key)
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

        scratch = _AgentTurnScratch()
        chat_id: str = ""
        exec_for_error: InboundMessage = msg
        is_resume = bool(msg.resume_value)
        inbound_had_voice = has_audio_attachment(msg) if not is_resume else False

        if inbound_had_voice:
            msg = await transcribe_inbound(msg, self._voice, self._bus.get_channel)
            exec_for_error = msg

        if msg.metadata.get("is_sticker") and self._sticker_vision:
            msg = await describe_sticker_inbound(
                msg, self._sticker_vision, self._bus.get_channel
            )
            exec_for_error = msg

        if not is_resume and has_video_attachment_fn(msg):
            msg = enrich_video_inbound(msg)
            exec_for_error = msg

        if not is_resume and has_image_attachment_fn(msg):
            msg = await enrich_image_inbound(msg, self._bus.get_channel)
            exec_for_error = msg

        agent_route_resolved = self._registry.resolve(msg.content)
        if (
            agent_route_resolved
            and agent_route_resolved.command_def.kind == CommandKind.AGENT_ROUTE
        ):
            agent_id = (
                agent_route_resolved.command_def.agent_id
                or agent_route_resolved.command_def.name
            )
            if agent_route_resolved.raw_args:
                msg = dataclasses.replace(msg, content=agent_route_resolved.raw_args)
                msg.metadata["route_agent_id"] = agent_id
            else:
                chat_id = msg.chat_id or msg.sender_id
                reply = OutboundMessage(
                    channel=msg.channel,
                    recipient_id=chat_id,
                    content=get_text(msg, "agent_route_switched", agent_id=agent_id),
                    user_id=msg.user_id or "",
                    thread_id=msg.thread_id,
                    reply_to_id=(
                        (msg.message_id or str(msg.metadata.get("message_id", "")))
                        if msg.is_group
                        else None
                    ),
                )
                await self._bus.publish_outbound(reply)
                set_correlation_context(None)  # Reset context
                return

        try:
            async with self._semaphore:
                try:
                    ctx = await self._prepare_execution_context(msg)
                    if ctx is None:
                        return

                    chat_id = ctx.chat_id
                    exec_for_error = ctx.exec_msg

                    rp = self._reaction_policy
                    if rp.should_processing:
                        await self._fx.ack_reaction(
                            msg.channel,
                            chat_id,
                            msg.message_id,
                            emoji=rp.processing_emoji,
                        )

                    await self._execute_prepared_context(
                        ctx,
                        scratch,
                        is_resume=is_resume,
                        inbound_had_voice=inbound_had_voice,
                    )

                    if scratch.completed and msg.message_id and rp.should_completion:
                        await self._fx.completion_reaction(
                            msg.channel,
                            chat_id,
                            msg.message_id,
                            success=True,
                            success_emoji=rp.completion_emoji,
                            failure_emoji=rp.failure_emoji,
                            had_ack=rp.should_processing,
                        )

                except Exception as e:
                    from app.channels.routing.message_effects import (
                        friendly_error_message,
                    )

                    friendly, ref_id = friendly_error_message(e, msg=exec_for_error)
                    logger.error(
                        "AgentRouter: failed to handle message from %s/%s [ref: %s]: %s",
                        exec_for_error.channel,
                        exec_for_error.sender_id,
                        ref_id,
                        e,
                        exc_info=e,
                    )
                    rp = self._reaction_policy
                    if msg.message_id and rp.should_completion:
                        await self._fx.completion_reaction(
                            exec_for_error.channel,
                            chat_id,
                            msg.message_id,
                            success=False,
                            success_emoji=rp.completion_emoji,
                            failure_emoji=rp.failure_emoji,
                            had_ack=rp.should_processing,
                        )
                    from app.channels.routing.placeholder_strategy import (
                        DeferredPlaceholder,
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
        finally:
            if self._inbound_journal and journal_entry_id:
                self._inbound_journal.acknowledge(journal_entry_id)
            self._gate.on_task_complete(msg)
