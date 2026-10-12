"""Unit tests for DesktopEnclaveService.

[POS]
Server unit tests verifying orchestration of desktop action evaluation,
challenge approvals/rejections, emergency panic activation, and Live Intent HUD feeds.
"""

from __future__ import annotations

from app.schemas.desktop_enclave import (
    ChallengeDecisionRequest,
    DesktopActionDto,
    EvaluateActionRequest,
)
from app.services.security.desktop_enclave_service import DesktopEnclaveService


def test_desktop_enclave_service_evaluation_and_decision() -> None:
    service = DesktopEnclaveService()

    # 1. Safe action passes through immediately
    safe_req = EvaluateActionRequest(
        action=DesktopActionDto(
            action_id="act_01",
            action_type="mouse_click",
            semantic_intent="点击导航菜单切换标签",
            coordinates=(100, 200),
            target_element_text="Navigation Tab",
        )
    )
    res_safe = service.evaluate_action(safe_req)
    assert res_safe.allowed is True
    assert res_safe.challenge is None

    # 2. Critical action is intercepted with challenge
    crit_req = EvaluateActionRequest(
        action=DesktopActionDto(
            action_id="act_02",
            action_type="mouse_click",
            semantic_intent="点击确认付款结账",
            target_element_text="立即支付",
        )
    )
    res_crit = service.evaluate_action(crit_req)
    assert res_crit.allowed is False
    assert res_crit.challenge is not None
    challenge_id = res_crit.challenge.challenge_id
    assert res_crit.challenge.status == "pending"

    # Verify pending challenge listing
    pending = service.get_pending_challenges()
    assert len(pending) == 1
    assert pending[0].challenge_id == challenge_id

    # 3. Approve challenge
    decide_res = service.decide_challenge(
        ChallengeDecisionRequest(challenge_id=challenge_id, approved=True, reason="User confirmed payment")
    )
    assert decide_res.status == "approved"
    assert decide_res.action is not None
    assert decide_res.action.action_id == "act_02"
    assert len(service.get_pending_challenges()) == 0

    # 4. Critical action rejected
    del_req = EvaluateActionRequest(
        action=DesktopActionDto(
            action_id="act_03",
            action_type="system_command",
            semantic_intent="清空回收站并永久删除",
        )
    )
    res_del = service.evaluate_action(del_req)
    assert res_del.allowed is False
    assert res_del.challenge is not None
    del_chal_id = res_del.challenge.challenge_id

    decide_del = service.decide_challenge(
        ChallengeDecisionRequest(challenge_id=del_chal_id, approved=False, reason="Deny destructive deletion")
    )
    assert decide_del.status == "rejected"
    assert decide_del.action is None


def test_desktop_enclave_service_panic_controls_and_hud() -> None:
    service = DesktopEnclaveService()

    # Initial state: not panicked
    status = service.get_panic_status()
    assert status.is_panicked is False

    # Trigger panic
    panic_res = service.trigger_panic(reason="User emergency stop button pressed")
    assert panic_res.is_panicked is True
    assert "emergency stop" in panic_res.panic_reason

    # Any evaluation while panicked returns allowed=False with panic reason
    eval_res = service.evaluate_action(
        EvaluateActionRequest(
            action=DesktopActionDto(
                action_id="act_panicked",
                action_type="mouse_click",
                semantic_intent="普通点击",
            )
        )
    )
    assert eval_res.allowed is False
    assert "Emergency panic active" in eval_res.reason

    # Reset panic
    reset_res = service.reset_panic()
    assert reset_res.is_panicked is False

    # HUD feed reflects recorded items
    feed = service.get_live_intent_feed(limit=10)
    assert feed.count >= 1
    assert len(feed.feed) >= 1
