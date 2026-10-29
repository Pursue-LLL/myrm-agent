"""Typing protocols: the host attributes and cross-mixin methods each pipeline mixin uses.

Each mixin of this package declares ``self: XxxHost`` for what it reads or calls on the ``AgentRouter``
instance, so it type-checks without importing the router (see also ``router_host.py`` for the other mixins).

[INPUT]
- channels.core.bus::MessageBus (POS: message routing hub between the channels and the router)
- channels.delegation::DelegationCoordinator (POS: delegated-task registry)
- channels.routing.command_defs::CommandAction, CommandDef (POS: slash command data model)
- channels.routing.command_registry::CommandRegistry, ResolvedCommand (POS: central O(1) command lookup)
- channels.routing.commands::ApprovalDecision, DenyWithReason, TopicCommand (POS: parsed slash-command arguments)
- channels.routing.placeholder_strategy::DeferredPlaceholder (POS: deferred placeholder handle)
- channels.routing.reactions::StatusReaction (POS: the reaction a turn shows on its message)
- channels.routing.router_models::_ActiveTask, _CleanupEntry, _AgentTurnScratch, _RouterExecutionContext, ReactionPolicy (POS: internal data classes)
- channels.protocols.*::LocaleProvider, SkillCommandHandler, TopicManager (POS: business-layer injection points)
- channels.types::InboundMessage, OutboundMessage, VoiceConfig, TopicContext (POS: channel message and routing types)

[OUTPUT]
- RouterLifecycleHost: structural contract for ``RouterLifecycleMixin``
- RouterInboundHost: structural contract for ``RouterInboundMixin``
- RouterCommandDispatchHost: structural contract for ``RouterCommandDispatchMixin``
- RouterTurnHost: structural contract for ``RouterTurnMixin``
- RouterDeliveryHost: structural contract for ``RouterDeliveryMixin``
- RouterExecutionHost: structural contract for ``RouterExecutionMixin``

[POS]
Typing protocols only, imported for annotations; nothing here runs. ``AgentRouter`` satisfies every protocol structurally.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
    from myrm_agent_harness.utils.runtime.steering import SteeringToken

    from app.channels.core.bus import MessageBus
    from app.channels.delegation import DelegationCoordinator
    from app.channels.media.sticker_vision import StickerVisionService
    from app.channels.protocols.locale import LocaleProvider
    from app.channels.protocols.skill_command import SkillCommandHandler
    from app.channels.protocols.topic import TopicManager
    from app.channels.reliability.inbound_journal import InboundJournal
    from app.channels.routing.command_defs import CommandAction, CommandDef
    from app.channels.routing.command_registry import CommandRegistry, ResolvedCommand
    from app.channels.routing.commands import ApprovalDecision, DenyWithReason, TopicCommand
    from app.channels.routing.message_effects import MessageEffects
    from app.channels.routing.pending_approvals import PendingApprovals
    from app.channels.routing.placeholder_strategy import DeferredPlaceholder
    from app.channels.routing.policy_resolver import PolicyResolver
    from app.channels.routing.reactions import StatusReaction
    from app.channels.routing.router_models import (
        ReactionPolicy,
        _ActiveTask,
        _AgentTurnScratch,
        _CleanupEntry,
        _RouterExecutionContext,
    )
    from app.channels.routing.session_gate import SessionGate
    from app.channels.routing.stream_manager import ProgressEstimator, StreamCoordinator
    from app.channels.types import InboundMessage, OutboundMessage, TopicContext, VoiceConfig


class RouterLifecycleHost(Protocol):
    """Structural contract for ``RouterLifecycleMixin`` (consume loop, janitor, stuck-task watchdog)."""

    _SESSION_STATE_TTL: float
    _NEW_SESSION_PEER_TTL: float
    _bus: MessageBus
    _fx: MessageEffects
    _gate: SessionGate
    _delegation_coordinator: DelegationCoordinator
    _active_tasks: dict[str, _ActiveTask]
    _cleanups: dict[str, _CleanupEntry]
    _pending_approvals: PendingApprovals
    _stream_coordinator: StreamCoordinator
    _progress_estimator: ProgressEstimator
    _new_session_peers: dict[str, float]
    _session_yolo: dict[str, tuple[float, int | None]]
    _session_personality: dict[str, str]
    _seen_messages: dict[str, float]
    _running: bool
    _task: asyncio.Task[None] | None
    _janitor_task: asyncio.Task[None] | None

    def is_consume_loop_alive(self) -> bool: ...

    def _journal_inbound(self, msg: InboundMessage) -> str | None: ...

    def _start_janitor(self) -> None: ...

    async def _stop_janitor(self) -> None: ...

    async def _janitor_loop(self) -> None: ...

    async def _janitor_sweep(self) -> None: ...

    def _cleanup_stale_session_state(self, now_monotonic: float) -> None: ...

    async def _reap_stuck_tasks(self, now: float) -> None: ...

    async def _consume_loop(self) -> None: ...

    async def _dispatch_inbound_message(self, msg: InboundMessage) -> None: ...


class RouterInboundHost(Protocol):
    """Structural contract for ``RouterInboundMixin`` (dedup, sender checks, routing of one inbound message)."""

    _bus: MessageBus
    _gate: SessionGate
    _registry: CommandRegistry
    _resolver: PolicyResolver
    _delegation_coordinator: DelegationCoordinator
    _active_tasks: dict[str, _ActiveTask]
    _topic_resolver: TopicManager | None
    _locale_provider: LocaleProvider | None
    _seen_messages: dict[str, float]

    async def _enrich_message_locale(self, msg: InboundMessage) -> InboundMessage: ...

    def _note_group_activity(self, msg: InboundMessage) -> None: ...

    def _claim_approval_input(self, msg: InboundMessage) -> bool: ...

    async def _claim_command(self, msg: InboundMessage) -> bool: ...

    async def _fire_event_triggers(self, msg: InboundMessage) -> None: ...

    async def _claim_delegation(self, msg: InboundMessage) -> bool: ...

    async def _claim_delegated_task_steering(self, msg: InboundMessage) -> bool: ...

    async def _divert_group_chatter(self, msg: InboundMessage) -> bool: ...

    def _reply_in_background(self, msg: InboundMessage, content: str, *, quote_in_group: bool = False) -> None: ...

    async def _check_admin_permission(self, msg: InboundMessage) -> bool: ...

    async def _is_sender_admitted(self, msg: InboundMessage) -> bool: ...

    async def _is_untrusted_event_sender(self, msg: InboundMessage) -> bool: ...

    def _is_duplicate(self, msg: InboundMessage) -> bool: ...

    async def _dispatch_resolved(self, msg: InboundMessage, resolved: ResolvedCommand) -> bool: ...

    @staticmethod
    def _is_bang_command(content: str | None) -> bool: ...

    async def _handle_bang_command(self, msg: InboundMessage) -> None: ...

    async def _handle_action_button_approval(self, msg: InboundMessage) -> None: ...

    async def _handle_approval_command(
        self,
        msg: InboundMessage,
        decision: ApprovalDecision | DenyWithReason | list[ApprovalDecision],
    ) -> None: ...

    def _is_reaction_approval_valid(self, msg: InboundMessage) -> bool: ...

    def _has_pending_approval(self, msg: InboundMessage) -> bool: ...

    async def _handle_delegation_inbound(self, msg: InboundMessage, clean_prompt: str) -> bool: ...


class RouterCommandDispatchHost(Protocol):
    """Structural contract for ``RouterCommandDispatchMixin`` (resolved slash command to its handler)."""

    _bus: MessageBus
    _gate: SessionGate
    _registry: CommandRegistry
    _skill_command_handler: SkillCommandHandler | None

    async def _check_admin_permission(self, msg: InboundMessage) -> bool: ...

    async def _dispatch_system_command(self, msg: InboundMessage, action: CommandAction, raw_args: str) -> bool: ...

    async def _handle_skill_command(self, msg: InboundMessage, cmd: CommandDef, raw_args: str) -> None: ...

    async def _handle_help_command(self, msg: InboundMessage) -> None: ...

    async def _cancel_active_task(self, msg: InboundMessage) -> None: ...

    async def _handle_new_session(self, msg: InboundMessage) -> None: ...

    async def _handle_compact(self, msg: InboundMessage, raw_args: str = "") -> None: ...

    async def _handle_retry(self, msg: InboundMessage) -> None: ...

    async def _handle_undo(self, msg: InboundMessage) -> None: ...

    async def _handle_yolo_command(self, msg: InboundMessage, action: tuple[str, int | None]) -> None: ...

    async def _handle_personality_command(self, msg: InboundMessage, style: str) -> None: ...

    async def _handle_topic_command(self, msg: InboundMessage, cmd: TopicCommand) -> None: ...

    async def _handle_draft_command(self, msg: InboundMessage, raw_args: str) -> None: ...

    async def _handle_goal_command(self, msg: InboundMessage, raw_args: str) -> None: ...

    async def _handle_subgoal_command(self, msg: InboundMessage, raw_args: str) -> None: ...

    async def _handle_steer_command(self, msg: InboundMessage, raw_args: str) -> None: ...

    async def _handle_queue_command(self, msg: InboundMessage, raw_args: str) -> None: ...

    async def _handle_background_command(self, msg: InboundMessage, raw_args: str) -> None: ...

    async def _handle_kanban_command(self, msg: InboundMessage, raw_args: str) -> None: ...

    async def _handle_memory_command(self, msg: InboundMessage, raw_args: str) -> None: ...

    async def _handle_learn_command(self, msg: InboundMessage, raw_args: str) -> None: ...

    async def _handle_handoff_command(self, msg: InboundMessage, raw_args: str) -> None: ...

    async def _handle_status_command(self, msg: InboundMessage) -> None: ...

    async def _handle_quota_command(self, msg: InboundMessage) -> None: ...


class RouterTurnHost(Protocol):
    """Structural contract for ``RouterTurnMixin`` (one merged message from the session gate to the agent run)."""

    _bus: MessageBus
    _fx: MessageEffects
    _gate: SessionGate
    _registry: CommandRegistry
    _resolver: PolicyResolver
    _semaphore: asyncio.Semaphore
    _inbound_journal: InboundJournal | None
    _reaction_policy: ReactionPolicy
    _session_yolo: dict[str, tuple[float, int | None]]
    _session_personality: dict[str, str]
    _sticker_vision: StickerVisionService | None
    _voice: VoiceConfig | None

    def _acknowledge_inbound(self, journal_entry_id: str | None) -> None: ...

    def _journal_inbound(self, msg: InboundMessage) -> str | None: ...

    def _apply_session_state(self, msg: InboundMessage) -> InboundMessage: ...

    async def _enrich_attachments(self, msg: InboundMessage, *, is_resume: bool, inbound_had_voice: bool) -> InboundMessage: ...

    def _apply_agent_route(self, msg: InboundMessage) -> InboundMessage | None: ...

    async def _report_turn_failure(
        self,
        error: Exception,
        *,
        msg: InboundMessage,
        exec_for_error: InboundMessage,
        chat_id: str,
        scratch: _AgentTurnScratch,
        status: StatusReaction | None,
    ) -> None: ...

    async def _handle_topic_command(self, msg: InboundMessage, cmd: TopicCommand) -> None: ...

    async def _prepare_execution_context(self, inbound: InboundMessage) -> _RouterExecutionContext | None: ...

    async def _retire_open_approval(self, ctx: _RouterExecutionContext) -> None: ...

    async def _execute_prepared_context(
        self,
        ctx: _RouterExecutionContext,
        scratch: _AgentTurnScratch,
        *,
        is_resume: bool,
        inbound_had_voice: bool,
    ) -> None: ...


class RouterDeliveryHost(Protocol):
    """Structural contract for ``RouterDeliveryMixin`` (effects, delivery, draft hold, cleanup of one turn)."""

    _bus: MessageBus
    _fx: MessageEffects
    _active_tasks: dict[str, _ActiveTask]
    _cleanups: dict[str, _CleanupEntry]
    _pending_approvals: PendingApprovals
    _reaction_policy: ReactionPolicy
    _voice: VoiceConfig | None

    def _register_cleanup(
        self,
        key: str,
        channel: str,
        chat_id: str,
        message_id: object,
        placeholder_id: str | None = None,
        *,
        msg: InboundMessage | None = None,
    ) -> None: ...

    async def _attach_web_handoff(self, result: OutboundMessage, msg: InboundMessage) -> OutboundMessage: ...

    async def _create_outbound_draft(
        self,
        result: OutboundMessage,
        original_msg: InboundMessage,
        chat_id: str,
        topic_ctx: TopicContext,
        placeholder_id: str | None,
    ) -> None: ...


class RouterExecutionHost(Protocol):
    """Structural contract for ``RouterExecutionMixin`` (prepare the context, run the turn)."""

    _bus: MessageBus
    _fx: MessageEffects
    _resolver: PolicyResolver
    _gate: SessionGate
    _active_tasks: dict[str, _ActiveTask]
    _new_session_peers: dict[str, float]
    _topic_resolver: TopicManager | None

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
        hold_reply: bool = False,
    ) -> tuple[OutboundMessage | None, float]: ...

    def _resolve_live_placeholder_id(self, state_key: str) -> str | None: ...

    async def _resolve_topic(self, msg: InboundMessage) -> TopicContext | None: ...

    async def _setup_message_effects(
        self,
        msg: InboundMessage,
        state_key: str,
        chat_id: str,
        message_id: str | None,
        is_resume: bool,
    ) -> DeferredPlaceholder | None: ...

    async def _deliver_agent_result(
        self,
        result: OutboundMessage | None,
        deferred: DeferredPlaceholder | None,
        msg: InboundMessage,
        chat_id: str,
        last_progress_at: float,
        inbound_had_voice: bool,
        topic_ctx: TopicContext | None = None,
    ) -> bool: ...

    async def _cleanup_effects(
        self,
        state_key: str,
        chat_id: str,
        channel: str,
        placeholder_id: str | None,
    ) -> None: ...
