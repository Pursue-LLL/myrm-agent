"""Adaptive Wakeup Service coordinating background settlement deliveries and bounded wakes.

[INPUT]
- myrm_agent_harness.agent.coordination.adaptive_wakeup::{AdaptiveWakeupRouter, HostActivityState, RoutingDecision, WakeupBudgetState, WakeupChannel, WakeupEvent, WakeupSourceType}
- app.services.chat.chat_service::ChatService
- app.services.event.app_event_bus::{AppEvent, AppEventType, get_event_bus}

[OUTPUT]
- AdaptiveWakeupService singleton coordinating settlement channel decisions,
  headless wakeups, in-flight injections, and human budget resets.

[POS]
- Bridge between background jobs / subagent settlements and the chat execution engine.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from myrm_agent_harness.agent.coordination.adaptive_wakeup import (
    AdaptiveWakeupRouter,
    HostActivityState,
    RoutingDecision,
    WakeupBudgetState,
    WakeupChannel,
    WakeupEvent,
)

from app.services.chat.chat_helpers import WAKEUP_MESSAGE_ID_PREFIX
from app.services.chat.chat_service import ChatService
from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

logger = logging.getLogger(__name__)


class AdaptiveWakeupService:
    """Singleton service driving adaptive settlement routing and bounded autonomous wakes."""

    _instance: AdaptiveWakeupService | None = None

    def __init__(self, default_max_consecutive_wakes: int = 3) -> None:
        self._router: AdaptiveWakeupRouter = AdaptiveWakeupRouter(
            default_max_consecutive_wakes=default_max_consecutive_wakes
        )

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

    def set_host_activity(self, session_id: str, state: HostActivityState) -> None:
        """Update host agent real-time activity (IDLE, BUSY, or STOPPED)."""
        self._router.set_host_activity(session_id, state)

    def get_host_activity(self, session_id: str) -> HostActivityState:
        """Query host agent real-time activity."""
        return self._router.get_host_activity(session_id)

    def record_human_turn(self, session_id: str) -> None:
        """Reset wake budget when human user sends a verified message."""
        self._router.record_human_turn(session_id)
        logger.info("Adaptive wake budget reset for session=%s following human turn", session_id)

    def record_user_stop(self, session_id: str) -> None:
        """Suppress subsequent autonomous wakes when user explicitly stops/cancels."""
        self._router.record_user_stop(session_id)
        logger.info("Adaptive wake suppressed for session=%s following user stop request", session_id)

    def get_budget_state(self, session_id: str) -> WakeupBudgetState:
        """Retrieve current session autonomous wake budget state."""
        return self._router.budget_tracker.get_budget_state(session_id)

    def drain_injected_events(self, session_id: str) -> list[WakeupEvent]:
        """Atomically retrieve and clear queued injected settlement events."""
        return self._router.drain_injected_events(session_id)

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

        # 2. Channel actions
        if decision.channel == WakeupChannel.SUPPRESS:
            logger.debug("Settlement suppressed for session=%s", session_id)
            return decision

        if decision.channel == WakeupChannel.INJECT:
            # Staged in router injected inboxes; host will consume at turn end / checkpoint
            logger.debug("Settlement injected for active session=%s", session_id)
            return decision

        if decision.channel == WakeupChannel.DEGRADE:
            # Budget exhausted: append notification to chat history so user can review and resume
            notice_content = (
                f"<system_notification type='adaptive_settlement_degraded' source_id='{event.source_id}'>\n"
                f"[{event.source_type.value.upper()}] {event.summary}\n"
                f"Autonomous wakeup paused: reached consecutive wake limit ({decision.consecutive_wakes}).\n"
                f"Please send a message to continue.\n"
                f"</system_notification>"
            )
            await ChatService.ensure_chat_and_append_user_message(
                chat_id=session_id,
                content=notice_content,
                sent_at=datetime.now(tz=UTC),
                sent_timezone="UTC",
                message_id=f"{WAKEUP_MESSAGE_ID_PREFIX}degraded_{event.source_id}",
                action_mode="general",
            )
            return decision

        if decision.channel == WakeupChannel.FOLLOWUP:
            # Append prompt for agent continuation
            status_desc = "succeeded" if event.success else "failed"
            continuation_prompt = (
                f"<system_notification type='adaptive_wakeup_followup' source_id='{event.source_id}'>\n"
                f"Background {event.source_type.value} '{event.source_id}' {status_desc}.\n"
                f"Summary: {event.summary}\n"
            )
            if event.error:
                continuation_prompt += f"Error: {event.error}\n"
            if event.exit_code is not None:
                continuation_prompt += f"Exit code: {event.exit_code}\n"
            continuation_prompt += (
                f"Autonomous wake turn ({decision.consecutive_wakes}/3). "
                f"Please inspect and proceed with the next step of the workflow.\n"
                f"</system_notification>"
            )

            await ChatService.ensure_chat_and_append_user_message(
                chat_id=session_id,
                content=continuation_prompt,
                sent_at=datetime.now(tz=UTC),
                sent_timezone="UTC",
                message_id=f"{WAKEUP_MESSAGE_ID_PREFIX}followup_{event.source_id}_{decision.consecutive_wakes}",
                action_mode="general",
            )

            # Trigger detached headless execution
            from app.services.agent.wakeup_handler import ServerWakeupHandler

            handler = ServerWakeupHandler()
            asyncio.create_task(handler._run_headless_agent(session_id, agent_id))

        return decision

    def reset_session(self, session_id: str) -> None:
        """Clear all session memory and budget tracking."""
        self._router.reset_session(session_id)


def get_adaptive_wakeup_service() -> AdaptiveWakeupService:
    """Helper to retrieve the global singleton AdaptiveWakeupService."""
    return AdaptiveWakeupService.get_instance()
