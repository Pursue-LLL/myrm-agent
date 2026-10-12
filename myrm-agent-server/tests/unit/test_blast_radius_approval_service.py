"""
[POS] tests/unit/test_blast_radius_approval_service.py
Unit tests for BlastRadiusApprovalService.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest

from app.schemas.blast_radius_approval import (
    BatchSpanItemDTO,
    EvaluateBatchSpansRequestDTO,
    EvaluateCommandApprovalRequestDTO,
    VerifyLaunchCodeRequestDTO,
)
from app.services.security.blast_radius_approval_service import (
    BlastRadiusApprovalService,
)


@pytest.fixture
def service() -> BlastRadiusApprovalService:
    return BlastRadiusApprovalService()


def test_evaluate_safe_command(service: BlastRadiusApprovalService) -> None:
    req = EvaluateCommandApprovalRequestDTO(
        command="git status",
        span_id="span-safe-01",
    )
    res = service.evaluate_command(req)

    assert res.span_id == "span-safe-01"
    assert res.command == "git status"
    assert res.is_destructive is False
    assert res.never_folded is False
    assert res.impact_preview is None
    assert res.launch_code is None
    assert "Enter" in res.allowed_shortcuts
    assert "y" in res.allowed_shortcuts


def test_evaluate_destructive_rm_command(service: BlastRadiusApprovalService) -> None:
    req = EvaluateCommandApprovalRequestDTO(
        command="rm -rf /tmp/cache_dir/*.tmp",
        span_id="span-dest-01",
    )
    res = service.evaluate_command(req)

    assert res.span_id == "span-dest-01"
    assert res.is_destructive is True
    assert res.never_folded is True
    assert res.impact_preview is not None
    assert res.impact_preview.estimated_files_count >= 1
    assert "Will delete" in res.impact_preview.summary


def test_evaluate_high_risk_launch_code_and_verification(
    service: BlastRadiusApprovalService,
) -> None:
    # 1. Evaluate force push requiring typed challenge code
    req = EvaluateCommandApprovalRequestDTO(
        command="git push --force origin production",
        span_id="span-force-push",
    )
    res = service.evaluate_command(req)

    assert res.is_destructive is True
    assert res.never_folded is True
    assert res.launch_code is not None
    assert res.launch_code.requires_challenge is True

    token = res.launch_code.challenge_token
    assert token is not None
    assert len(token) == 6
    # Enter key shortcut is disabled for launch code protected commands
    assert "Enter" not in res.allowed_shortcuts
    assert "Esc" in res.allowed_shortcuts

    # 2. Test verify with wrong code
    verify_fail = service.verify_launch_code(
        VerifyLaunchCodeRequestDTO(token=token, user_input="BAD_CODE")
    )
    assert verify_fail.is_valid is False
    assert "mismatch" in verify_fail.reason.lower()

    # 3. Test verify with correct code
    verify_succ = service.verify_launch_code(
        VerifyLaunchCodeRequestDTO(token=token, user_input=token)
    )
    assert verify_succ.is_valid is True
    assert "verified" in verify_succ.reason.lower()

    # 4. Test replay prevention
    verify_replay = service.verify_launch_code(
        VerifyLaunchCodeRequestDTO(token=token, user_input=token)
    )
    assert verify_replay.is_valid is False
    assert "already been consumed" in verify_replay.reason.lower()


def test_evaluate_batch_spans(service: BlastRadiusApprovalService) -> None:
    req = EvaluateBatchSpansRequestDTO(
        commands=[
            BatchSpanItemDTO(span_id="span-01", command="echo 'building assets'"),
            BatchSpanItemDTO(span_id="span-02", command="rm -rf /dist"),
            BatchSpanItemDTO(span_id="span-03", command="git log -n 5"),
        ]
    )
    res = service.evaluate_batch_spans(req)

    assert len(res.policies) == 3
    # Destructive span-02 must be isolated in its own single-element group
    assert ["span-02"] in res.decision_groups
    # Non-destructive items are batched together
    assert ["span-01", "span-03"] in res.decision_groups
