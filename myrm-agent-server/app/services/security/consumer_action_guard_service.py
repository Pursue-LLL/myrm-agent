"""
[POS] app/services/security/consumer_action_guard_service.py
[INPUT] myrm_agent_harness.core.security.consumer_action_guard, app.schemas.consumer_action_guard
[OUTPUT] ConsumerActionGuardService, get_consumer_action_guard_service

Thread-safe service managing consumer-grade real-world action safeguards, quantity sanity checks,
sliding-window velocity limiters, and daily spend ceilings.

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from myrm_agent_harness.core.security.consumer_action_guard import (
    ConsumerActionTypeEnum as HarnessActionTypeEnum,
)
from myrm_agent_harness.core.security.consumer_action_guard import (
    ConsumerGuardPolicy as HarnessPolicy,
)
from myrm_agent_harness.core.security.consumer_action_guard import (
    ConsumerOrderSpec,
    ConsumerRealWorldActionGuardSuite,
)

from app.schemas.consumer_action_guard import (
    ActionEvaluationVerdictEnum,
    ConsumerGuardMetricsResponse,
    ConsumerGuardPolicySchema,
    ConsumerOrderConfirmRequest,
    ConsumerOrderConfirmResponse,
    ConsumerOrderEvaluateRequest,
    ConsumerOrderEvaluateResponse,
)


class ConsumerActionGuardService:
    """Service enforcing consumer-grade real-world safety guards across agent orders."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._suite = ConsumerRealWorldActionGuardSuite()
        self._policies_by_agent: dict[str, HarnessPolicy] = {}

    def get_agent_policy(self, agent_id: str) -> ConsumerGuardPolicySchema:
        """Retrieve the active policy for an agent."""
        with self._lock:
            policy = self._policies_by_agent.get(agent_id, HarnessPolicy())

        return ConsumerGuardPolicySchema(
            max_item_quantity=policy.max_item_quantity,
            max_single_action_amount=policy.max_single_action_amount,
            velocity_window_seconds=policy.velocity_window_seconds,
            max_actions_per_window=policy.max_actions_per_window,
            daily_spend_ceiling=policy.daily_spend_ceiling,
            allowlisted_addresses=list(policy.allowlisted_addresses),
            allowlisted_phones=list(policy.allowlisted_phones),
            allowlisted_merchants=list(policy.allowlisted_merchants),
        )

    def set_agent_policy(
        self, agent_id: str, schema: ConsumerGuardPolicySchema
    ) -> ConsumerGuardPolicySchema:
        """Update safety boundaries and white-lists for an agent."""
        policy = HarnessPolicy(
            max_item_quantity=schema.max_item_quantity,
            max_single_action_amount=schema.max_single_action_amount,
            velocity_window_seconds=schema.velocity_window_seconds,
            max_actions_per_window=schema.max_actions_per_window,
            daily_spend_ceiling=schema.daily_spend_ceiling,
            allowlisted_addresses=list(schema.allowlisted_addresses),
            allowlisted_phones=list(schema.allowlisted_phones),
            allowlisted_merchants=list(schema.allowlisted_merchants),
        )
        with self._lock:
            self._policies_by_agent[agent_id] = policy

        return schema

    def evaluate_order(
        self, req: ConsumerOrderEvaluateRequest
    ) -> ConsumerOrderEvaluateResponse:
        """Evaluate consumer action order against multi-layered safety guardrails."""
        harness_action = HarnessActionTypeEnum(req.action_type.value)
        order_spec = ConsumerOrderSpec(
            order_id=req.order_id,
            agent_id=req.agent_id,
            action_type=harness_action,
            item_name=req.item_name,
            quantity=req.quantity,
            unit_price=req.unit_price,
            total_amount=req.total_amount,
            recipient_name=req.recipient_name,
            recipient_phone=req.recipient_phone,
            delivery_address=req.delivery_address,
            merchant_id=req.merchant_id,
            timestamp=time.time(),
            metadata=req.metadata,
        )

        with self._lock:
            policy = self._policies_by_agent.get(req.agent_id, HarnessPolicy())
            res = self._suite.evaluate_order(order_spec, policy)

        verdict_val = ActionEvaluationVerdictEnum(res.verdict.value)
        return ConsumerOrderEvaluateResponse(
            is_allowed=res.is_allowed,
            verdict=verdict_val,
            message=res.message,
            requires_hitl=res.requires_hitl,
            confirmation_card_summary=res.confirmation_card_summary,
        )

    def confirm_order(
        self, req: ConsumerOrderConfirmRequest
    ) -> ConsumerOrderConfirmResponse:
        """Confirm an approved order and decrement rolling daily budget."""
        harness_action = HarnessActionTypeEnum(req.action_type.value)
        order_spec = ConsumerOrderSpec(
            order_id=req.order_id,
            agent_id=req.agent_id,
            action_type=harness_action,
            item_name="",
            quantity=1,
            unit_price=req.total_amount,
            total_amount=req.total_amount,
            recipient_name="",
            recipient_phone="",
            delivery_address="",
            merchant_id="",
            timestamp=time.time(),
        )

        with self._lock:
            self._suite.confirm_and_record_order(order_spec)
            daily_spent = self._suite.get_agent_daily_spent(req.agent_id)

        return ConsumerOrderConfirmResponse(
            order_id=req.order_id,
            agent_id=req.agent_id,
            is_confirmed=True,
            current_daily_spent=daily_spent,
        )

    def get_metrics(self) -> ConsumerGuardMetricsResponse:
        """Retrieve consumer safety telemetry metrics."""
        with self._lock:
            m = self._suite.get_metrics()

        return ConsumerGuardMetricsResponse(
            total_evaluations=m.total_evaluations,
            autonomous_approvals=m.autonomous_approvals,
            hitl_confirmations_required=m.hitl_confirmations_required,
            velocity_blocks=m.velocity_blocks,
            budget_exceeded_blocks=m.budget_exceeded_blocks,
            address_blocks=m.address_blocks,
        )


_SERVICE_INSTANCE: Optional[ConsumerActionGuardService] = None
_SERVICE_LOCK = threading.Lock()


def get_consumer_action_guard_service() -> ConsumerActionGuardService:
    """Get singleton instance of ConsumerActionGuardService."""
    global _SERVICE_INSTANCE
    with _SERVICE_LOCK:
        if _SERVICE_INSTANCE is None:
            _SERVICE_INSTANCE = ConsumerActionGuardService()
        return _SERVICE_INSTANCE
