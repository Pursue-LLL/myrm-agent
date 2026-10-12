"""Unit tests for SideEffectGateService and PostRunAcceptanceService.

[POS]
Verifies server-level orchestration of pre-action tool interception, human approval token issuance,
idempotency receipt binding, and deterministic post-run quality checks.
"""

from __future__ import annotations

from myrm_agent_harness.core.security.side_effect_gate import (
    PreActionSideEffectGate,
    PreActionStatus,
)

from app.schemas.side_effect_gate import (
    AcceptanceEvaluationRequest,
    AcceptanceRuleDto,
    ActionReceiptCreateRequest,
)
from app.services.approvals.post_run_acceptance_service import (
    PostRunAcceptanceService,
)
from app.services.approvals.side_effect_gate_service import (
    SideEffectGateService,
)


def test_side_effect_gate_service_intercept_and_decision() -> None:
    gate = PreActionSideEffectGate()
    service = SideEffectGateService(gate=gate)
    session_id = "sess_server_test_01"

    # 1. Local tool evaluation
    local_eval = service.evaluate_tool_action(session_id, "read_file", {"path": "main.py"})
    assert local_eval.allowed is True
    assert local_eval.status == PreActionStatus.BYPASSED

    # 2. Mutating tool intercepted
    mutating_eval = service.evaluate_tool_action(
        session_id,
        "send_email",
        {"to": "customer@acme.com", "body": "Invoice notice"},
    )
    assert mutating_eval.allowed is False
    assert mutating_eval.status == PreActionStatus.PENDING
    assert mutating_eval.challenge is not None
    challenge_id = mutating_eval.challenge.challenge_id

    # 3. List pending challenges
    pending = service.list_pending_challenges()
    assert any(c.challenge_id == challenge_id for c in pending)

    # 4. Query single challenge
    detail = service.get_challenge(challenge_id)
    assert detail is not None
    assert detail.tool_name == "send_email"

    # 5. Approve challenge
    decision_resp = service.decide_challenge(
        challenge_id=challenge_id,
        decision="approve",
        reviewer_id="human_approver_1",
    )
    assert decision_resp.status == "approved"
    assert decision_resp.auth_token is not None

    # 6. Dispatch with single-use auth token -> allowed!
    authorized_eval = service.evaluate_tool_action(
        session_id,
        "send_email",
        {"to": "customer@acme.com", "body": "Invoice notice"},
        auth_token=decision_resp.auth_token,
    )
    assert authorized_eval.allowed is True
    assert authorized_eval.status == PreActionStatus.APPROVED


def test_side_effect_gate_service_rejection() -> None:
    gate = PreActionSideEffectGate()
    service = SideEffectGateService(gate=gate)
    session_id = "sess_reject_02"

    eval_res = service.evaluate_tool_action(session_id, "delete_database", {"db": "prod"})
    assert eval_res.challenge is not None
    challenge_id = eval_res.challenge.challenge_id

    rej_resp = service.decide_challenge(
        challenge_id=challenge_id,
        decision="reject",
        reviewer_id="security_officer",
        reason="Production database deletion is forbidden",
    )
    assert rej_resp.status == "rejected"
    assert "forbidden" in rej_resp.message


def test_side_effect_receipt_ledger_and_replay() -> None:
    gate = PreActionSideEffectGate()
    service = SideEffectGateService(gate=gate)
    session_id = "sess_receipt_03"
    tool_name = "stripe_charge"
    args = {"customer": "cus_12345", "amount": 250.0}

    eval_res = service.evaluate_tool_action(session_id, tool_name, args)
    assert eval_res.challenge is not None
    idem_key = eval_res.idempotency_key

    # Record provider receipt
    receipt_dto = service.record_receipt(
        ActionReceiptCreateRequest(
            idempotency_key=idem_key,
            tool_name=tool_name,
            provider_receipt_id="ch_stripe_999888777",
            output_summary="Charge succeeded for $250.00",
            challenge_id=eval_res.challenge.challenge_id,
        )
    )
    assert receipt_dto.provider_receipt_id == "ch_stripe_999888777"

    # Query receipt
    fetched_receipt = service.get_receipt(idem_key)
    assert fetched_receipt is not None
    assert fetched_receipt.provider_receipt_id == "ch_stripe_999888777"

    # Replay check via gate evaluation
    replay_eval = service.evaluate_tool_action(session_id, tool_name, args)
    assert replay_eval.allowed is True
    assert replay_eval.status == PreActionStatus.BYPASSED
    assert replay_eval.cached_receipt is not None
    assert replay_eval.cached_receipt.provider_receipt_id == "ch_stripe_999888777"


def test_post_run_acceptance_service_text_and_structured() -> None:
    service = PostRunAcceptanceService()

    # 1. Text acceptance evaluation
    text_req = AcceptanceEvaluationRequest(
        text_content=(
            "# Project Delivery Report\n"
            "This sprint deliverable meets all specified acceptance criteria.\n\n"
            "## Architecture & Design\n"
            "Implemented two-phase separation of execution and acceptance.\n\n"
            "## Test Verification\n"
            "All unit and end-to-end tests passed."
        ),
        rules=[
            AcceptanceRuleDto(
                rule_type="non_empty",
                description="Deliverable must not be empty",
            ),
            AcceptanceRuleDto(
                rule_type="length_bounds",
                description="Must be at least 50 characters",
                min_length=50,
            ),
            AcceptanceRuleDto(
                rule_type="required_structure",
                description="Must contain all required sections",
                required_sections=["# Project Delivery Report", "## Architecture & Design", "## Test Verification"],
            ),
        ],
    )
    text_resp = service.evaluate(text_req)
    assert text_resp.passed is True
    assert len(text_resp.violations) == 0

    # 2. Structured acceptance evaluation (mathematical consistency)
    struct_req = AcceptanceEvaluationRequest(
        structured_payload={
            "order_id": "ORD-2026-900",
            "items": [
                {"name": "Database Cluster", "amount": 1200.0},
                {"name": "Load Balancer", "amount": 300.0},
            ],
            "total_cost": 1500.0,
        },
        rules=[
            AcceptanceRuleDto(
                rule_type="required_json_keys",
                description="Order payload required keys",
                required_json_keys=["order_id", "items", "total_cost"],
            ),
            AcceptanceRuleDto(
                rule_type="numerical_sum_equals",
                description="Cost items must sum to total_cost",
                sum_field_names=["items"],
                total_field_name="total_cost",
            ),
        ],
    )
    struct_resp = service.evaluate(struct_req)
    assert struct_resp.passed is True
    assert len(struct_resp.violations) == 0
