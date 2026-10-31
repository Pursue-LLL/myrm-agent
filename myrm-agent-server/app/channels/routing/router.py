"""Agent router — routes inbound channel messages to Agent execution.

Consumes InboundMessage from the MessageBus, applies DM/group policy,
resolves the sender's identity, executes the Agent via AgentExecutor,
and publishes the result as an OutboundMessage.

Supports slash commands (see command_defs.SYSTEM_COMMANDS). Those that act on the owner's sandbox (/memory, /goal, /bind,
/draft, ...) run only for the owner; the few marked ``any_sender`` (/stop, /new, /help, ...) stay open to every sender.
Also supports voice STT/TTS via voice_handler module.


[INPUT]
- channels.core.bus::MessageBus (POS: async message bus)
- channels.routing.pipeline::RouterLifecycleMixin, RouterInboundMixin, RouterCommandDispatchMixin, RouterTurnMixin, RouterExecutionMixin (POS: the router's run loop, inbound routing, command dispatch, turn handling and execution; execution builds on pipeline.delivery::RouterDeliveryMixin for effects, delivery and cleanup)
- channels.routing.router_stream::RouterStreamMixin (POS: execute_stream consumption and placeholder throttled editing)
- channels.routing.commands::RouterCommandsMixin (POS: slash-command handlers, including /stop, approval, topic and /draft)
- channels.routing.command_registry::CommandRegistry (POS: central O(1) command lookup)
- channels.routing.command_defs::CommandDef (POS: slash command data model)
- channels.routing.policy_resolver::PolicyResolver (POS: DM/group policy resolution + identity resolution)
- channels.routing.session_gate::SessionGate (POS: message debounce and concurrency control)
- channels.routing.context_buffer::GroupContextBuffer (POS: group chat context accumulation buffer)
- channels.routing.message_effects::MessageEffects (POS: typing/reaction/placeholder side effects)
- channels.routing.pending_approvals::PendingApprovals (POS: the router's registry of tool approvals a chat is waiting on)
- channels.routing.router_constants::_MAX_CONCURRENT_AGENTS (POS: concurrency limit)
- channels.routing.router_host::PersonalityProvider (POS: typing protocol for the business-layer personality templates)
- channels.routing.router_models::_ActiveTask, _CleanupEntry, ReactionPolicy (POS: internal data classes)
- channels.protocols.*::AgentExecutor, CompactHandler, GoalCommandHandler, SkillCommandHandler, LearnCommandHandler, RetryHandler, UndoHandler, PairingStore, ChannelPolicyProvider, TopicManager (POS: business-layer injection points)

[OUTPUT]
- AgentRouter: inbound message routing hub composed from the mixins above; it owns construction and the state they share (active tasks, cleanups, pending approvals, dedup map, session yolo/personality, session gate, streaming stack)
- _ActiveTask, _CleanupEntry, _RouterExecutionContext, _AgentTurnScratch: see `router_models.py`
- Concurrency and dedup constants: see `router_constants.py`

[POS]
Core inbound message routing hub. Connects MessageBus (inbound queue) to agent executor
with symmetric inbound risk gate (complements outbound risk gate in bus.py).
The behavior lives in the mixins, in the order a message meets it: `RouterLifecycleMixin`
(consume loop, janitor), `RouterInboundMixin` (dedup, sender checks, routing of one message),
`RouterCommandDispatchMixin` (slash command to handler), `RouterTurnMixin` (`_handle_merged`),
`RouterExecutionMixin` (prepare, run the turn), `RouterDeliveryMixin` (effects, reply delivery),
`RouterStreamMixin` (stream consumption), `RouterCommandsMixin` (command handlers).
Uses PolicyResolver to check DM/group policies and resolve user identity;
group policies may rewrite InboundMessage (prefix stripping, context_messages, etc.),
with the rewritten message stored in `_RouterExecutionContext.exec_msg`. After successful
`prepare`, `_execute_prepared_context` handles active task registration, side effects,
streaming execution, and result delivery.
A turn ends for `SessionGate` when `_handle_merged` returns. `_execute_prepared_context`
records the session (`gate_key(exec_msg)`) and turn id on `_ActiveTask`, so the stuck-task
watchdog releases that exact turn; the key depends only on channel, peer and topic, which
neither STT nor group rewriting change.
Slash commands are handled via the commands module, completing the bidirectional conversation loop.
Manages active task mapping, approval message IDs, and cleanup janitor.
Each mixin uses Protocol constraints (`router_host`, `pipeline/hosts`) for the `self` attributes it needs.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.channels.routing.router_host import (
        PersonalityProvider,
    )


from app.channels.core.bus import MessageBus
from app.channels.delegation import (
    DelegationCoordinator,
    DelegationIngressGuard,
)
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
from app.channels.reliability.inbound_journal import (
    InboundJournal,
)
from app.channels.routing.command_defs import (
    CommandDef,
)
from app.channels.routing.command_registry import (
    CommandRegistry,
)
from app.channels.routing.commands import (
    RouterCommandsMixin,
)
from app.channels.routing.context_buffer import (
    GroupContextBuffer,
)
from app.channels.routing.graceful_degradation import (
    GracefulDegradationController,
)
from app.channels.routing.message_effects import MessageEffects
from app.channels.routing.pending_approvals import PendingApprovals
from app.channels.routing.pipeline import (
    RouterCommandDispatchMixin,
    RouterExecutionMixin,
    RouterInboundMixin,
    RouterLifecycleMixin,
    RouterTurnMixin,
)
from app.channels.routing.policy_resolver import PolicyResolver
from app.channels.routing.retry_policy import (
    RetryConfig as RouterRetryConfig,
)
from app.channels.routing.retry_policy import (
    RetryPolicy,
)
from app.channels.routing.router_constants import (
    _MAX_CONCURRENT_AGENTS,
)
from app.channels.routing.router_models import (
    ReactionPolicy,
    _ActiveTask,
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
    VoiceConfig,
)

logger = logging.getLogger(__name__)


class AgentRouter(
    RouterLifecycleMixin,
    RouterInboundMixin,
    RouterCommandDispatchMixin,
    RouterTurnMixin,
    RouterExecutionMixin,
    RouterStreamMixin,
    RouterCommandsMixin,
):
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
        kanban_handler: KanbanCommandHandler | None = None,
        learn_handler: LearnCommandHandler | None = None,
        status_provider: StatusProvider | None = None,
        extra_commands: tuple[CommandDef, ...] = (),
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
        self._kanban_handler = kanban_handler
        self._learn_handler = learn_handler
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
        bus.set_sender_gate(self._is_sender_admitted)
        bus.set_owner_gate(self._check_admin_permission)
        self._semaphore = asyncio.Semaphore(_MAX_CONCURRENT_AGENTS)
        self._gate = SessionGate(
            session_gate_config or SessionGateConfig(),
            on_ready=self._handle_merged,
            on_busy_ack=self._fx.send_busy_ack,
        )
        self._task: asyncio.Task[None] | None = None
        self._active_tasks: dict[str, _ActiveTask] = {}
        self._cleanups: dict[str, _CleanupEntry] = {}
        self._pending_approvals = PendingApprovals(on_expire=self._resume_after_approval_timeout)
        self._approval_co_approvers: frozenset[str] = approval_co_approvers or frozenset()
        self._janitor_task: asyncio.Task[None] | None = None
        self._seen_messages: dict[str, float] = {}
        self._new_session_peers: dict[str, float] = {}
        self._session_yolo: dict[str, tuple[float, int | None]] = {}
        self._session_personality: dict[str, str] = {}
        self._personality_provider = personality_provider
        self._running = False
        self._stream_metrics = StreamMetrics()
        self._locale_provider = locale_provider
        self._delegation_coordinator = DelegationCoordinator()
        self._delegation_guard = DelegationIngressGuard()

        stream_config = stream_config or StreamConfig()
        self._session_rate_limiter = SessionRateLimiter(max_updates_per_minute=60)
        self._degradation_controller = GracefulDegradationController(
            failure_threshold=3,
            success_threshold=2,
            max_level=4,
        )

        self._progress_estimator = ProgressEstimator(session_ttl_seconds=stream_config.progress_session_ttl_seconds)

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

    def set_reaction_policy(self, policy: ReactionPolicy) -> None:
        """Replace reaction policy at runtime (e.g. after channels config save)."""
        self._reaction_policy = policy

    @property
    def delegation_coordinator(self) -> DelegationCoordinator:
        """Access the delegation coordinator instance."""
        return self._delegation_coordinator
