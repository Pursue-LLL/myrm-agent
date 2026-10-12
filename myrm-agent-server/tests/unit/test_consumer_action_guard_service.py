"""
[POS] tests/unit/test_consumer_action_guard_service.py
[INPUT] app.schemas.consumer_action_guard, app.services.security.consumer_action_guard_service
[OUTPUT] unit tests

Unit tests for ConsumerActionGuardService.
Strict typing applied: No `Any` types allowed.
"""

from app.schemas.consumer_action_guard import (
    ActionEvaluationVerdictEnum,
    ConsumerActionTypeEnum,
    ConsumerGuardPolicySchema,
    ConsumerOrderConfirmRequest,
    ConsumerOrderEvaluateRequest,
)
from app.services.security.consumer_action_guard_service import (
    ConsumerActionGuardService,
)


def test_service_policy_and_autonomous_allow() -> None:
    service = ConsumerActionGuardService()
    agent_id = "agent-consumer-test-1"

    # Set custom policy with allowlisted address and phone
    policy = ConsumerGuardPolicySchema(
        max_item_quantity=3,
        max_single_action_amount=50.0,
        velocity_window_seconds=300.0,
        max_actions_per_window=2,
        daily_spend_ceiling=150.0,
        allowlisted_addresses=["123 Main St, Suite 400"],
        allowlisted_phones=["+1-555-0199"],
        allowlisted_merchants=["merchant-abc"],
    )
    service.set_agent_policy(agent_id, policy)
    fetched = service.get_agent_policy(agent_id)
    assert fetched.max_item_quantity == 3
    assert fetched.max_single_action_amount == 50.0
    assert "123 Main St, Suite 400" in fetched.allowlisted_addresses

    # Evaluate compliant order
    req = ConsumerOrderEvaluateRequest(
        order_id="ord-001",
        agent_id=agent_id,
        action_type=ConsumerActionTypeEnum.FOOD_DELIVERY,
        item_name="Warm Lunch Bowl",
        quantity=2,
        unit_price=15.0,
        total_amount=30.0,
        recipient_name="Alice Smith",
        recipient_phone="+1-555-0199",
        delivery_address="123 Main St, Suite 400",
        merchant_id="merchant-abc",
        metadata={"category": "lunch"},
    )
    res = service.evaluate_order(req)
    assert res.is_allowed is True
    assert res.verdict == ActionEvaluationVerdictEnum.ALLOW_AUTONOMOUS
    assert res.requires_hitl is False
    assert res.confirmation_card_summary is None

    # Confirm order and update daily spent
    confirm_req = ConsumerOrderConfirmRequest(
        order_id="ord-001",
        agent_id=agent_id,
        action_type=ConsumerActionTypeEnum.FOOD_DELIVERY,
        total_amount=30.0,
    )
    confirm_res = service.confirm_order(confirm_req)
    assert confirm_res.is_confirmed is True
    assert confirm_res.current_daily_spent == 30.0

    # Metrics inspection
    metrics = service.get_metrics()
    assert metrics.total_evaluations == 1
    assert metrics.autonomous_approvals == 1


def test_service_quantity_sanity_and_hitl_escalation() -> None:
    service = ConsumerActionGuardService()
    agent_id = "agent-grandma-burrito-test"

    # Evaluate excessive quantity order (e.g. 50 burritos)
    req = ConsumerOrderEvaluateRequest(
        order_id="ord-002",
        agent_id=agent_id,
        action_type=ConsumerActionTypeEnum.FOOD_DELIVERY,
        item_name="Breakfast Burrito",
        quantity=50,
        unit_price=8.0,
        total_amount=400.0,
        recipient_name="Grandma Smith",
        recipient_phone="+1-555-0100",
        delivery_address="742 Evergreen Terrace",
        merchant_id="burrito-bar",
    )
    res = service.evaluate_order(req)
    assert res.is_allowed is False
    assert res.verdict == ActionEvaluationVerdictEnum.REQUIRES_HUMAN_CONFIRMATION
    assert res.requires_hitl is True
    assert res.confirmation_card_summary is not None
    assert "Action Confirmation Required" in res.confirmation_card_summary
    assert "Breakfast Burrito x 50" in res.confirmation_card_summary

    metrics = service.get_metrics()
    assert metrics.hitl_confirmations_required >= 1


def test_service_untrusted_address_and_velocity_blocks() -> None:
    service = ConsumerActionGuardService()
    agent_id = "agent-velocity-test"

    policy = ConsumerGuardPolicySchema(
        max_item_quantity=5,
        max_single_action_amount=100.0,
        velocity_window_seconds=600.0,
        max_actions_per_window=1,
        daily_spend_ceiling=200.0,
        allowlisted_addresses=["Verified Home Address"],
        allowlisted_phones=["+1-555-1111"],
    )
    service.set_agent_policy(agent_id, policy)

    # 1. Untrusted address
    bad_addr_req = ConsumerOrderEvaluateRequest(
        order_id="ord-bad-addr",
        agent_id=agent_id,
        action_type=ConsumerActionTypeEnum.FOOD_DELIVERY,
        item_name="Salad",
        quantity=1,
        unit_price=15.0,
        total_amount=15.0,
        recipient_name="Bob",
        recipient_phone="+1-555-1111",
        delivery_address="Unknown Warehouse Alley 99",
        merchant_id="salad-co",
    )
    bad_res = service.evaluate_order(bad_addr_req)
    assert bad_res.is_allowed is False
    assert bad_res.verdict == ActionEvaluationVerdictEnum.UNTRUSTED_ADDRESS_BLOCKED

    # 2. First legitimate order allowed and confirmed
    good_req1 = ConsumerOrderEvaluateRequest(
        order_id="ord-good-1",
        agent_id=agent_id,
        action_type=ConsumerActionTypeEnum.FOOD_DELIVERY,
        item_name="Salad",
        quantity=1,
        unit_price=15.0,
        total_amount=15.0,
        recipient_name="Bob",
        recipient_phone="+1-555-1111",
        delivery_address="Verified Home Address",
        merchant_id="salad-co",
    )
    good_res1 = service.evaluate_order(good_req1)
    assert good_res1.is_allowed is True

    service.confirm_order(
        ConsumerOrderConfirmRequest(
            order_id="ord-good-1",
            agent_id=agent_id,
            action_type=ConsumerActionTypeEnum.FOOD_DELIVERY,
            total_amount=15.0,
        )
    )

    # 3. Second order immediately exceeds velocity limit (max 1 per 600s)
    good_req2 = ConsumerOrderEvaluateRequest(
        order_id="ord-good-2",
        agent_id=agent_id,
        action_type=ConsumerActionTypeEnum.FOOD_DELIVERY,
        item_name="Sandwich",
        quantity=1,
        unit_price=12.0,
        total_amount=12.0,
        recipient_name="Bob",
        recipient_phone="+1-555-1111",
        delivery_address="Verified Home Address",
        merchant_id="salad-co",
    )
    good_res2 = service.evaluate_order(good_req2)
    assert good_res2.is_allowed is False
    assert good_res2.verdict == ActionEvaluationVerdictEnum.VELOCITY_RATE_LIMITED
