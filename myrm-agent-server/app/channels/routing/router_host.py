"""Typing protocols: host instance attributes required by Router Mixins.

Each Mixin uses ``self: XxxHost`` to declare the attributes it reads/writes
on the AgentRouter instance, enabling static type checking without circular imports.

[INPUT]
- app.channels.types::InboundMessage, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)
- app.channels.core.bus::MessageBus (POS: Message routing hub. Producers call publish_outbound; the bus dispatches by priority to the target channel (SYSTEM > NORMAL > BULK). Inbound messages enter the _inbound queue via channel _emit_inbound callbacks, consumed by AgentRouter. Outbound messages are auto-downgraded before dispatch for channels lacking interactive component support: components are rendered as text appended to content; quick_replies only downgrade ``required=True`` items, silently dropping non-required ones.)
- app.channels.protocols.agent::AgentExecutor (POS: Agent execution protocol for Channel inbound messages. Framework AgentRouter delegates inbound messages to business-layer Agents via this protocol. execute_stream returns AsyncGenerator yielding ProgressUpdate (progress) and OutboundMessage (final result). External cancellation (e.g. user /stop command)。)
- app.channels.protocols.compact::CompactHandler (POS: Business-layer handler protocol for the /compact slash command. Framework parses user_id and invokes handler; business layer implements DB, Chat service, and compact logic.)
- app.channels.protocols.topic::TopicManager (POS: Topic Supports two binding granularities Telegram forum topics)
- app.channels.protocols.turn_management::RetryHandler, UndoHandler (POS: Business-layer handler protocol for /retry and /undo slash commands. Symmetric design with CompactHandler: framework parses user_id, business layer handles DB operations.)
- utils.runtime.cancellation::CancellationToken (POS: Agent  ContextVar  BaseAgent)

[OUTPUT]
- RouterStreamHost: Structural contract for `RouterStreamMixin` (execute_stre...
- PersonalityInfo: Minimal personality template info required by the command...
- PersonalityProvider: Business-layer injectable personality template provider.
- RouterCommandsHost: Structural contract for `RouterCommandsMixin` (/stop, app...
- RouterExecutionHost: Structural contract for `RouterExecutionMixin` (prepare, ...

[POS]
Typing protocols: host instance attributes required by Router Mixins.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
    from myrm_agent_harness.utils.runtime.steering import SteeringToken

    from app.channels.core.bus import MessageBus
    from app.channels.protocols.agent import AgentExecutor
    from app.channels.protocols.background_task import BackgroundTaskHandler
    from app.channels.protocols.compact import CompactHandler
    from app.channels.protocols.goal_command import GoalCommandHandler
    from app.channels.protocols.kanban_command import KanbanCommandHandler
    from app.channels.protocols.status import StatusProvider
    from app.channels.protocols.topic import TopicManager
    from app.channels.protocols.turn_management import RetryHandler, UndoHandler
    from app.channels.routing.graceful_degradation import (
        GracefulDegradationController,
    )
    from app.channels.routing.message_effects import MessageEffects
    from app.channels.routing.policy_resolver import PolicyResolver
    from app.channels.routing.retry_policy import RetryPolicy
    from app.channels.routing.router_models import (
        ReactionPolicy,
        _ActiveTask,
        _CleanupEntry,
    )
    from app.channels.routing.session_gate import SessionGate
    from app.channels.routing.session_rate_limiter import SessionRateLimiter
    from app.channels.routing.stream_manager import (
        ProgressEstimator,
        StreamCoordinator,
    )
    from app.channels.routing.stream_metrics import StreamMetrics
    from app.channels.types import (
        InboundMessage,
        OutboundMessage,
        ProgressUpdate,
        TopicContext,
        VoiceConfig,
    )


class RouterStreamHost(Protocol):
    """Structural contract for `RouterStreamMixin` (execute_stream consumption, throttled edits)."""

    _executor: AgentExecutor
    _bus: MessageBus
    _fx: MessageEffects
    _approval_msg_ids: dict[str, str]
    _stream_coordinator: StreamCoordinator
    _progress_estimator: ProgressEstimator
    _stream_metrics: StreamMetrics
    _degradation_controller: GracefulDegradationController
    _session_rate_limiter: SessionRateLimiter
    _retry_policy: RetryPolicy

    async def _send_interactive_progress(
        self,
        msg: InboundMessage,
        chat_id: str,
        progress: ProgressUpdate,
    ) -> str | None: ...

    async def _try_throttled_edit(
        self,
        placeholder_id: str | None,
        content: str,
        last_edit_at: float,
        min_interval: float,
        channel: str,
        chat_id: str,
    ) -> float | None: ...


class PersonalityInfo(Protocol):
    """Minimal personality template info required by the command handler."""

    name: str
    emoji: str
    display_name: str
    display_name_zh: str
    description_zh: str


class PersonalityProvider(Protocol):
    """Business-layer injectable personality template provider."""

    def list_all(self) -> list[PersonalityInfo]: ...
    def get(self, style: str) -> PersonalityInfo | None: ...


class RouterCommandsHost(Protocol):
    """Structural contract for `RouterCommandsMixin` (/stop, approvals, session/topic/retry/undo commands)."""

    _bus: MessageBus
    _fx: MessageEffects
    _active_tasks: dict[str, _ActiveTask]
    _gate: SessionGate
    _approval_msg_ids: dict[str, str]
    _approval_co_approvers: frozenset[str]
    _compact_handler: CompactHandler | None
    _retry_handler: RetryHandler | None
    _undo_handler: UndoHandler | None
    _resolver: PolicyResolver
    _new_session_peers: dict[str, float]
    _topic_resolver: TopicManager | None
    _session_yolo: dict[str, tuple[float, int | None]]
    _session_personality: dict[str, str]
    _personality_provider: PersonalityProvider | None
    _goal_handler: GoalCommandHandler | None
    _background_handler: BackgroundTaskHandler | None
    _kanban_handler: KanbanCommandHandler | None
    _status_provider: StatusProvider | None


class RouterExecutionHost(Protocol):
    """Structural contract for `RouterExecutionMixin` (prepare, effects, stream, deliver, cleanup)."""

    _bus: MessageBus
    _fx: MessageEffects
    _resolver: PolicyResolver
    _active_tasks: dict[str, _ActiveTask]
    _cleanups: dict[str, _CleanupEntry]
    _approval_msg_ids: dict[str, str]
    _new_session_peers: dict[str, float]
    _topic_resolver: TopicManager | None
    _voice: VoiceConfig | None
    _reaction_policy: ReactionPolicy

    async def _consume_executor_stream(
        self,
        msg: InboundMessage,
        user_id: str,
        state_key: str,
        chat_id: str,
        *,
        cancel_token: CancellationToken | None = None,
        steering_token: SteeringToken | None = None,
        topic_context: TopicContext | None = None,
    ) -> tuple[OutboundMessage | None, float]: ...

    def _resolve_live_placeholder_id(self, state_key: str) -> str | None: ...
