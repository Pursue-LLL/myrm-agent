"""Adaptive wakeup router deciding between followup, degradation, or suppression.

Routes background asynchronous settlements by the user's stop flag and the bounded
consecutive wake budget. A settlement only reads the budget; the host spends one unit
when a wake turn actually starts, so settlements that share one turn cost one wake.

[INPUT]
- budget_tracker::WakeupBudgetTracker (POS: per-session consecutive-wake budget and the user's stop flag)
- types::RoutingDecision, WakeupChannel, WakeupEvent (POS: typed settlement events and routing outcomes)

[OUTPUT]
- AdaptiveWakeupRouter: decides what a settled background task does to its session (followup / degrade / suppress) and spends the wake budget of a turn the host starts

[POS]
Adaptive wakeup router deciding between followup, degradation, or suppression.
"""

from .budget_tracker import WakeupBudgetTracker
from .types import RoutingDecision, WakeupChannel, WakeupEvent


class AdaptiveWakeupRouter:
    """Orchestrates settlement delivery channel selection for asynchronous tasks."""

    def __init__(
        self,
        budget_tracker: WakeupBudgetTracker | None = None,
        default_max_consecutive_wakes: int = 3,
    ) -> None:
        self._tracker: WakeupBudgetTracker = (
            budget_tracker if budget_tracker is not None else WakeupBudgetTracker(default_max_consecutive_wakes)
        )

    @property
    def budget_tracker(self) -> WakeupBudgetTracker:
        """The underlying budget tracker instance."""
        return self._tracker

    def record_human_turn(self, session_id: str) -> None:
        """Notify router of an explicit human interaction turn, resetting wake budget."""
        self._tracker.record_human_turn(session_id)

    def record_user_stop(self, session_id: str) -> None:
        """Notify router of an explicit user stop/cancellation request."""
        self._tracker.record_user_stop(session_id)

    def route(self, event: WakeupEvent) -> RoutingDecision:
        """Determine settlement delivery channel for an asynchronous completion event."""
        budget_state = self._tracker.get_budget_state(event.session_id)

        # 1. The user stopped the session: nothing may start a turn on its own
        if budget_state.is_user_stopped:
            return RoutingDecision(
                channel=WakeupChannel.SUPPRESS,
                reason="Suppressed: user requested stop or session execution was cancelled",
                session_id=event.session_id,
                source_id=event.source_id,
                consecutive_wakes=budget_state.consecutive_wakes,
                budget_remaining=budget_state.budget_remaining,
            )

        # 2. Followup while the autonomous wake budget lasts, degradation once it is spent
        if not budget_state.is_exhausted:
            return RoutingDecision(
                channel=WakeupChannel.FOLLOWUP,
                reason=(
                    f"Followup: autonomous wake budget available "
                    f"({budget_state.consecutive_wakes}/{budget_state.max_consecutive_wakes} used)"
                ),
                session_id=event.session_id,
                source_id=event.source_id,
                consecutive_wakes=budget_state.consecutive_wakes,
                budget_remaining=budget_state.budget_remaining,
            )

        return RoutingDecision(
            channel=WakeupChannel.DEGRADE,
            reason=(
                f"Degraded: consecutive autonomous wake budget exhausted "
                f"({budget_state.consecutive_wakes}/{budget_state.max_consecutive_wakes}), "
                "awaiting human input"
            ),
            session_id=event.session_id,
            source_id=event.source_id,
            consecutive_wakes=budget_state.consecutive_wakes,
            budget_remaining=budget_state.budget_remaining,
        )

    def claim_wake_turn(self, session_id: str) -> bool:
        """Spend one wake of the budget for a wake turn about to start; False when none is left or the user stopped."""
        return self._tracker.consume_wake_budget(session_id)

    def reset_session(self, session_id: str) -> None:
        """Clear all router state for a session."""
        self._tracker.reset_session(session_id)
