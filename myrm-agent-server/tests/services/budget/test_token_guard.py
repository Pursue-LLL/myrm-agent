"""Unit tests for single-task token budget guard service."""

from app.services.budget.token_guard import GuardStatus, TaskTokenGuard


def test_token_guard_normal_progression() -> None:
    guard = TaskTokenGuard(hard_limit=10000, soft_limit_ratio=0.8)
    eval_res = guard.record_turn_usage(prompt_tokens=2000, completion_tokens=1000)

    assert eval_res.status == GuardStatus.NORMAL
    assert eval_res.total_tokens == 3000
    assert eval_res.prompt_tokens == 2000
    assert eval_res.completion_tokens == 1000
    assert eval_res.is_paused is False


def test_token_guard_soft_limit_warning() -> None:
    guard = TaskTokenGuard(hard_limit=10000, soft_limit_ratio=0.8)
    # 8500 tokens >= 8000 soft limit
    eval_res = guard.record_turn_usage(prompt_tokens=5000, completion_tokens=3500)

    assert eval_res.status == GuardStatus.WARNING_SOFT_CAP
    assert eval_res.total_tokens == 8500
    assert eval_res.is_paused is False
    assert eval_res.message is not None
    assert "soft warning threshold" in eval_res.message


def test_token_guard_hard_cap_breach() -> None:
    guard = TaskTokenGuard(hard_limit=10000, soft_limit_ratio=0.8)
    eval_res = guard.record_turn_usage(prompt_tokens=6000, completion_tokens=4500)

    assert eval_res.status == GuardStatus.BREACH_HARD_CAP
    assert eval_res.total_tokens == 10500
    assert eval_res.is_paused is True
    assert eval_res.message is not None
    assert "hard limit" in eval_res.message


def test_token_guard_user_override_extension() -> None:
    guard = TaskTokenGuard(hard_limit=10000, soft_limit_ratio=0.8)
    guard.record_turn_usage(prompt_tokens=6000, completion_tokens=4500)
    assert guard.total_tokens == 10500

    # User clicks "extend by 5000 tokens"
    guard.grant_extension(5000)
    eval_res = guard.record_turn_usage(prompt_tokens=0, completion_tokens=0)

    # 10500 is now below new hard limit 15000, but still above new soft limit 12000? 10500 < 12000 -> normal
    assert eval_res.status == GuardStatus.NORMAL
    assert eval_res.is_paused is False
    assert eval_res.hard_limit == 15000
