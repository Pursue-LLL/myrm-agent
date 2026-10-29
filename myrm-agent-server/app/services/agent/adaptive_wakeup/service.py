"""Adaptive Wakeup Service coordinating background settlement deliveries and bounded wakes.

[INPUT]
- myrm_agent_harness.agent.coordination.adaptive_wakeup::{AdaptiveWakeupRouter, RoutingDecision, WakeupBudgetState, WakeupChannel, WakeupEvent} (POS: bounded consecutive-wake budget and the followup / degrade / suppress decision)
- myrm_agent_harness.agent.security.guards.estop::check_estop (POS: the emergency stop keeps wake turns from starting)
- app.services.agent.adaptive_wakeup.reply_return::return_wake_reply (POS: hands the reply of a finished wake turn to whoever carries it back outside the app)
- app.services.agent.adaptive_wakeup.settled_results::SettledResults (POS: which settlements a wake turn answers and which of their results the agent already read)
- app.services.agent.adaptive_wakeup.wake_turn_scheduler::schedule_wake_turn (POS: starts the one wake turn once the chat is free)
- app.services.agent.adaptive_wakeup.wake_turn_stream::stream_wake_turn (POS: builds the chat's agent and streams the wake turn)
- app.services.budget.enforcer::should_block_execution (POS: the daily spend limit keeps wake turns from starting)
- app.services.chat.chat_service::ChatService (POS: chat business facade; appends the notice row)
- app.services.event.app_event_bus::{AppEvent, AppEventType, get_event_bus} (POS: in-process event bus the UI listens to)
- app.database.models.chat::WAKEUP_NOTICE_* (POS: how a notice row says which kind of settlement it is)

[OUTPUT]
- AdaptiveWakeupService singleton coordinating settlement channel decisions, wake turns, the user's stop flag and
  human budget resets.

[POS]
- Bridge between background jobs / subagent settlements and the chat execution engine.
  Every settlement lands in the chat as a notice row, whatever channel it takes, so the next turn sees it.
  A settlement only reads the wake budget; a wake turn spends one unit of it when it actually starts.
  A wake turn whose every result the agent already read in its own turn does not start. What a wake turn says is also
  returned to the place outside the app where its chat was started, when there is one.
"""

from __future__ import annotations

import html
import logging
from collections.abc import Iterable
from datetime import UTC, datetime

from myrm_agent_harness.agent.coordination.adaptive_wakeup import (
    AdaptiveWakeupRouter,
    RoutingDecision,
    WakeupBudgetState,
    WakeupChannel,
    WakeupEvent,
)
from myrm_agent_harness.agent.security.guards.estop import check_estop
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

from app.database.models.chat import (
    WAKEUP_NOTICE_DEGRADED,
    WAKEUP_NOTICE_FOLLOWUP,
    WAKEUP_NOTICE_KEY,
    WAKEUP_NOTICE_SUPPRESSED,
)
from app.services.agent.adaptive_wakeup.reply_return import return_wake_reply
from app.services.agent.adaptive_wakeup.settled_results import SettledResults
from app.services.agent.adaptive_wakeup.wake_turn_scheduler import schedule_wake_turn
from app.services.agent.adaptive_wakeup.wake_turn_stream import stream_wake_turn
from app.services.budget.enforcer import should_block_execution
from app.services.chat.chat_helpers import WAKEUP_MESSAGE_ID_PREFIX
from app.services.chat.chat_service import ChatService
from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

logger = logging.getLogger(__name__)

_NOTICE_KIND = {
    WakeupChannel.FOLLOWUP: WAKEUP_NOTICE_FOLLOWUP,
    WakeupChannel.DEGRADE: WAKEUP_NOTICE_DEGRADED,
    WakeupChannel.SUPPRESS: WAKEUP_NOTICE_SUPPRESSED,
}
_NOTICE_TYPE = {
    WakeupChannel.FOLLOWUP: "adaptive_wakeup_followup",
    WakeupChannel.DEGRADE: "adaptive_settlement_degraded",
    WakeupChannel.SUPPRESS: "adaptive_settlement_suppressed",
}

# Summaries and errors come from tool and sub-agent output; the notice keeps the head of them.
_MAX_NOTICE_TEXT_CHARS = 600
_MAX_NOTICE_SOURCE_ID_CHARS = 120


def _notice_text(value: str, limit: int = _MAX_NOTICE_TEXT_CHARS, *, quote: bool = False) -> str:
    """Bound ``value`` and escape it, so settled output cannot close the notice or open a notice of its own."""
    bounded = value if len(value) <= limit else f"{value[:limit]}..."
    return html.escape(bounded, quote=quote)


def _notice_message_id(event: WakeupEvent, decision: RoutingDecision) -> str:
    """Row id of the notice; the prefix keeps it apart from what the user typed."""
    return f"{WAKEUP_MESSAGE_ID_PREFIX}{_NOTICE_KIND[decision.channel]}_{event.source_id}"


def _notice_content(event: WakeupEvent, decision: RoutingDecision) -> str:
    """The system notification the model reads for a settlement, by what the router decided to do with it."""
    source = event.source_type.value
    source_id = _notice_text(event.source_id, _MAX_NOTICE_SOURCE_ID_CHARS, quote=True)
    summary = _notice_text(event.summary)
    if decision.channel == WakeupChannel.FOLLOWUP:
        status_desc = "succeeded" if event.success else "failed"
        body = f"Background {source} '{source_id}' {status_desc}.\nSummary: {summary}\n"
        if event.error:
            body += f"Error: {_notice_text(event.error)}\n"
        if event.exit_code is not None:
            body += f"Exit code: {event.exit_code}\n"
        body += (
            f"Autonomous wake turn ({decision.consecutive_wakes + 1}/"
            f"{decision.consecutive_wakes + decision.budget_remaining}). "
            "Please inspect and proceed with the next step of the workflow.\n"
        )
    elif decision.channel == WakeupChannel.DEGRADE:
        body = (
            f"[{source.upper()}] {summary}\n"
            f"Autonomous wakeup paused: reached consecutive wake limit ({decision.consecutive_wakes}).\n"
            "Please send a message to continue.\n"
        )
    else:
        body = (
            f"[{source.upper()}] {summary}\n"
            "Autonomous wakeup skipped: the user stopped this session. Please send a message to continue.\n"
        )
    return f"<system_notification type='{_NOTICE_TYPE[decision.channel]}' source_id='{source_id}'>\n{body}</system_notification>"


class AdaptiveWakeupService:
    """Singleton service driving adaptive settlement routing and bounded autonomous wakes."""

    _instance: AdaptiveWakeupService | None = None

    def __init__(self, default_max_consecutive_wakes: int = 3) -> None:
        self._router: AdaptiveWakeupRouter = AdaptiveWakeupRouter(default_max_consecutive_wakes=default_max_consecutive_wakes)
        self._settled = SettledResults()

    @classmethod
    def get_instance(cls) -> AdaptiveWakeupService:
        """Access the global singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def router(self) -> AdaptiveWakeupRouter:
        """Underlying router engine."""
        return self._router

    def record_human_turn(self, chat_id: str) -> None:
        """Reset the wake budget and lift a stop when the user sends a message."""
        self._router.record_human_turn(chat_id)
        logger.debug("Adaptive wake budget reset for session=%s following human turn", chat_id)

    def record_user_stop(self, chat_id: str) -> None:
        """Keep settlements from starting a turn on their own until the user writes again."""
        self._router.record_user_stop(chat_id)
        logger.info("Adaptive wake suppressed for session=%s following user stop request", chat_id)

    def get_budget_state(self, chat_id: str) -> WakeupBudgetState:
        """Retrieve current session autonomous wake budget state."""
        return self._router.budget_tracker.get_budget_state(chat_id)

    def note_results_read(self, chat_id: str, task_ids: Iterable[str]) -> None:
        """The agent read these settled results in a tool call of its own, so no wake turn needs to deliver them."""
        self._settled.mark_read(chat_id, task_ids)

    def forget_chat(self, chat_id: str) -> None:
        """Drop the wake budget, stop flag and unanswered settlements of a chat that is gone."""
        self._router.reset_session(chat_id)
        self._settled.forget(chat_id)

    async def handle_settlement(self, event: WakeupEvent) -> RoutingDecision | None:
        """Route a settlement of ``event.session_id`` (a chat id) and queue the wake turn it calls for.

        Returns ``None`` when the chat no longer exists: a settlement must not bring a deleted chat back.
        """
        chat_id = event.session_id
        if await ChatService.get_chat_metadata(chat_id) is None:
            logger.info(
                "Settlement dropped, the chat no longer exists: source=%s:%s session=%s",
                event.source_type.value,
                event.source_id,
                chat_id,
            )
            return None

        decision = self._router.route(event)
        logger.info(
            "AdaptiveWakeup routed event source=%s:%s session=%s channel=%s reason='%s'",
            event.source_type.value,
            event.source_id,
            chat_id,
            decision.channel.value,
            decision.reason,
        )

        # 1. Publish system notification event for UI awareness
        get_event_bus().publish(
            AppEvent(
                event_type=AppEventType.SYSTEM_NOTIFICATION,
                data={
                    "title": f"Asynchronous Settlement ({decision.channel.value.upper()})",
                    "message": f"[{event.source_type.value}] {event.summary} - {decision.reason}",
                    "meta_data": {
                        "session_id": chat_id,
                        "source_id": event.source_id,
                        "source_type": event.source_type.value,
                        "channel": decision.channel.value,
                        "consecutive_wakes": decision.consecutive_wakes,
                        "budget_remaining": decision.budget_remaining,
                    },
                },
            )
        )

        # 2. The chat keeps every settlement as a notice row, so the next turn (woken or typed) sees it
        await ChatService.ensure_chat_and_append_user_message(
            chat_id=chat_id,
            content=_notice_content(event, decision),
            sent_at=datetime.now(tz=UTC),
            sent_timezone="UTC",
            message_id=_notice_message_id(event, decision),
            action_mode="general",
            extra_data={WAKEUP_NOTICE_KEY: _NOTICE_KIND[decision.channel]},
        )

        # 3. Only a followup starts a turn; it waits for the chat to be free and shares one turn with its neighbours
        if decision.channel == WakeupChannel.FOLLOWUP:
            self._settled.queue(chat_id, event.source_id)
            schedule_wake_turn(chat_id, self._run_wake_turn)

        return decision

    async def _run_wake_turn(self, chat_id: str, turn_id: str, cancel_token: CancellationToken, settled_at: datetime) -> None:
        """Start the wake turn the scheduler holds the chat for, unless the situation changed while it waited."""
        # Before any await: a settlement that lands from here on belongs to the next wake turn.
        results_read = self._settled.take_all_read(chat_id)
        if (reason := await self._skip_reason(chat_id, settled_at, results_read=results_read)) is not None:
            logger.info("Wake turn skipped, %s: session=%s", reason, chat_id)
            return
        if (reply := await stream_wake_turn(chat_id, turn_id, cancel_token)) is not None:
            await return_wake_reply(chat_id, reply)

    async def _skip_reason(self, chat_id: str, settled_at: datetime, *, results_read: bool) -> str | None:
        """Why the wake turn must not start now (``None`` to start it, spending one unit of the wake budget).

        The settlement was routed earlier; the user may have stopped, written, or switched everything off since, and
        the agent may have read every result the turn would deliver.
        """
        if check_estop() is not None:
            return "the emergency stop is on"
        state = self.get_budget_state(chat_id)
        if state.is_user_stopped:
            return "the user stopped the session"
        if state.last_human_reset_time is not None and state.last_human_reset_time > settled_at:
            return "the user wrote after the notice"
        if results_read:
            return "the agent already read every result this turn would deliver"
        if await should_block_execution():
            return "the daily budget is exceeded"
        # Claimed last: a turn that does not start must not use up the budget.
        if not self._router.claim_wake_turn(chat_id):
            return "the wake budget is spent"
        return None


def get_adaptive_wakeup_service() -> AdaptiveWakeupService:
    """Helper to retrieve the global singleton AdaptiveWakeupService."""
    return AdaptiveWakeupService.get_instance()
