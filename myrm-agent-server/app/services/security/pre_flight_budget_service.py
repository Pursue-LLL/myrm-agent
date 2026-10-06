"""Service layer for Live Pre-Flight Budget Chokepoint Suite.

[INPUT]
myrm_agent_harness.core.security.pre_flight_budget::PreFlightBudgetChokepoint, LiveBudgetStore, BudgetBroadcastBus
app.schemas.pre_flight_budget::BudgetConfigCreateRequest, RecordSpendRequest, EvaluateBudgetRequest

[OUTPUT]
PreFlightBudgetService: Singleton business service coordinating live pre-flight budget chokepoints and event bus.

[POS]
运行前预算卡点业务服务层。协调 Harness 预算卡点评估、滑动时间窗口支出记录与实时事件总线广播。
"""

from __future__ import annotations

import logging
from typing import ClassVar

from myrm_agent_harness.core.security.pre_flight_budget import (
    BudgetAction,
    BudgetBroadcastBus,
    BudgetDecision,
    BudgetExceededViolationError,
    BudgetPeriod,
    LiveBudgetStore,
    PreFlightBudgetChokepoint,
)

from app.schemas.pre_flight_budget import (
    BudgetActionEnum,
    BudgetBroadcastEventResponse,
    BudgetConfigCreateRequest,
    BudgetConfigResponse,
    BudgetDecisionResponse,
    BudgetPeriodEnum,
    QueueAllowedResponse,
    RecordSpendRequest,
    SpendRecordResponse,
)

logger = logging.getLogger(__name__)


class PreFlightBudgetService:
    """Business service coordinating live pre-flight budget chokepoints and event bus."""

    _instance: ClassVar[PreFlightBudgetService | None] = None

    def __init__(
        self,
        chokepoint: PreFlightBudgetChokepoint | None = None,
    ) -> None:
        if chokepoint is not None:
            self._chokepoint = chokepoint
        else:
            store = LiveBudgetStore()
            bus = BudgetBroadcastBus()
            self._chokepoint = PreFlightBudgetChokepoint(store=store, bus=bus)

    @classmethod
    def get_instance(cls) -> PreFlightBudgetService:
        """Obtain singleton service instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton service instance for test isolation."""
        cls._instance = None

    def set_config(
        self, request: BudgetConfigCreateRequest
    ) -> BudgetConfigResponse:
        """Configure or update live project budget."""
        period_mapping = {
            BudgetPeriodEnum.DAILY: BudgetPeriod.DAILY,
            BudgetPeriodEnum.SESSION: BudgetPeriod.SESSION,
            BudgetPeriodEnum.TOTAL: BudgetPeriod.TOTAL,
        }
        action_mapping = {
            BudgetActionEnum.PAUSE: BudgetAction.PAUSE,
            BudgetActionEnum.STOP: BudgetAction.STOP,
        }

        cfg = self._chokepoint.store.set_config(
            project_id=request.project_id,
            limit_amount=request.limit_amount,
            currency=request.currency,
            period=period_mapping[request.period],
            action=action_mapping[request.action],
            anchor_timestamp=request.anchor_timestamp,
        )

        return BudgetConfigResponse(
            project_id=cfg.project_id,
            limit_amount=cfg.limit_amount,
            currency=cfg.currency,
            period=request.period,
            action=request.action,
            anchor_timestamp=cfg.anchor_timestamp,
        )

    def get_config(self, project_id: str) -> BudgetConfigResponse | None:
        """Retrieve live configuration for a project."""
        cfg = self._chokepoint.store.get_config(project_id)
        if cfg is None:
            return None

        return BudgetConfigResponse(
            project_id=cfg.project_id,
            limit_amount=cfg.limit_amount,
            currency=cfg.currency,
            period=BudgetPeriodEnum(cfg.period.value),
            action=BudgetActionEnum(cfg.action.value),
            anchor_timestamp=cfg.anchor_timestamp,
        )

    def record_spend(self, request: RecordSpendRequest) -> SpendRecordResponse:
        """Record an LLM call spend in the project ledger."""
        rec = self._chokepoint.record_spend(
            project_id=request.project_id,
            amount=request.amount,
            currency=request.currency,
            model_name=request.model_name,
            source=request.source,
        )
        return SpendRecordResponse(
            project_id=rec.project_id,
            amount=rec.amount,
            currency=rec.currency,
            model_name=rec.model_name,
            source=rec.source,
            timestamp=rec.timestamp,
        )

    def _convert_decision(self, decision: BudgetDecision) -> BudgetDecisionResponse:
        return BudgetDecisionResponse(
            tripped=decision.tripped,
            action=BudgetActionEnum(decision.action.value),
            project_id=decision.project_id,
            current_spend=decision.current_spend,
            limit=decision.limit,
            currency=decision.currency,
            period=BudgetPeriodEnum(decision.period.value),
            reason=decision.reason,
        )

    def evaluate(self, project_id: str) -> BudgetDecisionResponse:
        """Evaluate live budget status without raising exceptions."""
        decision = self._chokepoint.evaluate(project_id)
        return self._convert_decision(decision)

    def enforce(self, project_id: str) -> BudgetDecisionResponse:
        """Enforce pre-flight budget chokepoint, returning decision or catching violation."""
        try:
            decision = self._chokepoint.enforce_pre_flight(project_id)
            return self._convert_decision(decision)
        except BudgetExceededViolationError as e:
            return self._convert_decision(e.decision)

    def is_queue_dispatch_allowed(self, project_id: str) -> QueueAllowedResponse:
        """Verify if queue dispatcher can dispatch sub-tasks."""
        allowed = self._chokepoint.is_queue_dispatch_allowed(project_id)
        decision = self._chokepoint.evaluate(project_id)
        reason = (
            "Dispatch permitted"
            if allowed
            else f"Queue locked: project {project_id} spend {decision.current_spend:.4f} >= limit {decision.limit:.4f}"
        )
        return QueueAllowedResponse(
            project_id=project_id,
            queue_dispatch_allowed=allowed,
            reason=reason,
        )

    def get_events(
        self, project_id: str | None = None, limit: int = 50
    ) -> list[BudgetBroadcastEventResponse]:
        """Fetch recent broadcast events."""
        events = self._chokepoint.bus.get_history(project_id=project_id, limit=limit)
        return [
            BudgetBroadcastEventResponse(
                event_type=e.event_type.value,
                project_id=e.project_id,
                timestamp=e.timestamp,
                payload=e.payload,
            )
            for e in events
        ]
