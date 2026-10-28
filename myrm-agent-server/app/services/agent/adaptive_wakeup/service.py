"""Adaptive Wakeup Service coordinating background settlement deliveries and bounded wakes.

[INPUT]
- myrm_agent_harness.agent.coordination.adaptive_wakeup::{AdaptiveWakeupRouter, RoutingDecision, WakeupBudgetState, WakeupChannel, WakeupEvent} (POS: bounded consecutive-wake budget and the followup / degrade / suppress decision)
- app.services.agent.adaptive_wakeup.wake_turn_scheduler::schedule_wake_turn (POS: starts the one wake turn once the chat is free)
- app.services.chat.chat_service::ChatService (POS: chat business facade; appends the notice row)
- app.services.event.app_event_bus::{AppEvent, AppEventType, get_event_bus} (POS: in-process event bus the UI listens to)

[OUTPUT]
- AdaptiveWakeupService singleton coordinating settlement channel decisions,
  wake turns, the user's stop flag, and human budget resets.

[POS]
- Bridge between background jobs / subagent settlements and the chat execution engine.
  Every settlement lands in the chat as a notice row, whatever channel it takes, so the next turn sees it.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from myrm_agent_harness.agent.coordination.adaptive_wakeup import (
    AdaptiveWakeupRouter,
    RoutingDecision,
    WakeupBudgetState,
    WakeupChannel,
    WakeupEvent,
)

from app.services.agent.adaptive_wakeup.wake_turn_scheduler import schedule_wake_turn
from app.services.chat.chat_helpers import WAKEUP_MESSAGE_ID_PREFIX
from app.services.chat.chat_service import ChatService
from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

logger = logging.getLogger(__name__)

_NOTICE_KIND = {
    WakeupChannel.FOLLOWUP: "followup",
    WakeupChannel.DEGRADE: "degraded",
    WakeupChannel.SUPPRESS: "suppressed",
}
_NOTICE_TYPE = {
    WakeupChannel.FOLLOWUP: "adaptive_wakeup_followup",
    WakeupChannel.DEGRADE: "adaptive_settlement_degraded",
    WakeupChannel.SUPPRESS: "adaptive_settlement_suppressed",
}


def _notice_message_id(event: WakeupEvent, decision: RoutingDecision) -> str:
    """Row id of the notice; the prefix keeps it apart from what the user typed."""
    suffix = f"_{decision.consecutive_wakes}" if decision.channel == WakeupChannel.FOLLOWUP else ""
    return f"{WAKEUP_MESSAGE_ID_PREFIX}{_NOTICE_KIND[decision.channel]}_{event.source_id}{suffix}"


def _notice_content(event: WakeupEvent, decision: RoutingDecision) -> str:
    """The system notification the model reads for a settlement, by what the router decided to do with it."""
    source = event.source_type.value
    if decision.channel == WakeupChannel.FOLLOWUP:
        status_desc = "succeeded" if event.success else "failed"
        body = f"Background {source} '{event.source_id}' {status_desc}.\nSummary: {event.summary}\n"
        if event.error:
            body += f"Error: {event.error}\n"
        if event.exit_code is not None:
            body += f"Exit code: {event.exit_code}\n"
        body += (
            f"Autonomous wake turn ({decision.consecutive_wakes}/3). "
            "Please inspect and proceed with the next step of the workflow.\n"
        )
    elif decision.channel == WakeupChannel.DEGRADE:
        body = (
            f"[{source.upper()}] {event.summary}\n"
            f"Autonomous wakeup paused: reached consecutive wake limit ({decision.consecutive_wakes}).\n"
            "Please send a message to continue.\n"
        )
    else:
        body = (
            f"[{source.upper()}] {event.summary}\n"
            "Autonomous wakeup skipped: the user stopped this session. Please send a message to continue.\n"
        )
    return f"<system_notification type='{_NOTICE_TYPE[decision.channel]}' source_id='{event.source_id}'>\n{body}</system_notification>"


class AdaptiveWakeupService:
    """Singleton service driving adaptive settlement routing and bounded autonomous wakes."""

    _instance: AdaptiveWakeupService | None = None

    def __init__(self, default_max_consecutive_wakes: int = 3) -> None:
        self._router: AdaptiveWakeupRouter = AdaptiveWakeupRouter(default_max_consecutive_wakes=default_max_consecutive_wakes)

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

    def record_human_turn(self, session_id: str) -> None:
        """Reset the wake budget and lift a stop when the user sends a message."""
        self._router.record_human_turn(session_id)
        logger.debug("Adaptive wake budget reset for session=%s following human turn", session_id)

    def record_user_stop(self, session_id: str) -> None:
        """Keep settlements from starting a turn on their own until the user writes again."""
        self._router.record_user_stop(session_id)
        logger.info("Adaptive wake suppressed for session=%s following user stop request", session_id)

    def get_budget_state(self, session_id: str) -> WakeupBudgetState:
        """Retrieve current session autonomous wake budget state."""
        return self._router.budget_tracker.get_budget_state(session_id)

    async def handle_settlement(
        self,
        event: WakeupEvent,
        agent_id: str = "general_agent",
    ) -> RoutingDecision:
        """Route an asynchronous settlement event and trigger headless continuation if needed."""
        decision = self._router.route(event)
        session_id = event.session_id

        logger.info(
            "AdaptiveWakeup routed event source=%s:%s session=%s channel=%s reason='%s'",
            event.source_type.value,
            event.source_id,
            session_id,
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
                        "session_id": session_id,
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
            chat_id=session_id,
            content=_notice_content(event, decision),
            sent_at=datetime.now(tz=UTC),
            sent_timezone="UTC",
            message_id=_notice_message_id(event, decision),
            action_mode="general",
        )

        # 3. Only a followup starts a turn; it waits for the chat to be free and shares one turn with its neighbours
        if decision.channel == WakeupChannel.FOLLOWUP:
            schedule_wake_turn(session_id, agent_id)

        return decision

    def reset_session(self, session_id: str) -> None:
        """Clear all session memory and budget tracking."""
        self._router.reset_session(session_id)


def get_adaptive_wakeup_service() -> AdaptiveWakeupService:
    """Helper to retrieve the global singleton AdaptiveWakeupService."""
    return AdaptiveWakeupService.get_instance()
