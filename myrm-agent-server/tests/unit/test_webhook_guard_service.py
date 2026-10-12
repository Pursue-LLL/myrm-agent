"""Unit tests for WebhookGuardService in server layer.

[POS]
Server unit tests verifying webhook origin taint processing, dynamic tool masking,
interactive admin approval card generation, and post-approval elevation.
"""

from __future__ import annotations

from app.schemas.webhook_guard import (
    EvaluateExecutionRequest,
    FilterToolsetRequest,
    OriginTaintDto,
)
from app.services.security.webhook_guard_service import WebhookGuardService


def test_webhook_guard_service_filter_tools() -> None:
    service = WebhookGuardService()
    all_tools = ["web_search", "web_extract", "bash_code_execute", "file_write"]

    # 1. Untainted context
    clean_res = service.filter_toolset(
        FilterToolsetRequest(
            all_tools=all_tools,
            taint=OriginTaintDto(
                is_untrusted_external_content=False,
                origin_source="cron_internal",
                sender_identity="system",
            ),
        )
    )
    assert clean_res.allowed_tools == all_tools
    assert len(clean_res.demoted_tools) == 0
    assert clean_res.is_tainted is False

    # 2. Tainted context
    tainted_res = service.filter_toolset(
        FilterToolsetRequest(
            all_tools=all_tools,
            taint=OriginTaintDto(
                is_untrusted_external_content=True,
                origin_source="github_issue",
                sender_identity="external_user",
            ),
        )
    )
    assert "bash_code_execute" in tainted_res.demoted_tools
    assert "file_write" in tainted_res.demoted_tools
    assert "web_search" in tainted_res.allowed_tools
    assert tainted_res.is_tainted is True


def test_webhook_guard_service_evaluate_and_approve_card() -> None:
    service = WebhookGuardService()
    task_id = "task_webhook_eval_01"
    taint = OriginTaintDto(
        is_untrusted_external_content=True,
        origin_source="github_pr",
        sender_identity="adversary_tester",
    )

    # 1. Safe tool is permitted
    safe_eval = service.evaluate_execution(
        EvaluateExecutionRequest(
            task_id=task_id,
            tool_name="web_search",
            tool_arguments={"query": "security"},
            taint=taint,
        )
    )
    assert safe_eval.allowed is True
    assert safe_eval.requires_approval is False

    # 2. Dangerous tool escalates to approval card
    danger_eval = service.evaluate_execution(
        EvaluateExecutionRequest(
            task_id=task_id,
            tool_name="bash_code_execute",
            tool_arguments={"command": "npm install malicious-pkg"},
            taint=taint,
        )
    )
    assert danger_eval.allowed is False
    assert danger_eval.requires_approval is True
    assert danger_eval.card is not None
    assert danger_eval.card.status == "pending"
    card_id = danger_eval.card.card_id

    # 3. Approve card
    approved_dto = service.approve_card(card_id)
    assert approved_dto.status == "approved"

    # 4. Re-evaluate same dangerous tool now succeeds
    post_eval = service.evaluate_execution(
        EvaluateExecutionRequest(
            task_id=task_id,
            tool_name="bash_code_execute",
            tool_arguments={"command": "npm install malicious-pkg"},
            taint=taint,
        )
    )
    assert post_eval.allowed is True
    assert post_eval.requires_approval is False


def test_webhook_guard_service_reject_card() -> None:
    service = WebhookGuardService()
    task_id = "task_webhook_reject_02"
    taint = OriginTaintDto(
        is_untrusted_external_content=True,
        origin_source="public_form",
        sender_identity="anon",
    )

    danger_eval = service.evaluate_execution(
        EvaluateExecutionRequest(
            task_id=task_id,
            tool_name="file_write",
            tool_arguments={"path": "/etc/shadow", "content": "root::0:0:::"},
            taint=taint,
        )
    )
    card_id = danger_eval.card.card_id if danger_eval.card else ""
    assert card_id != ""

    rejected_dto = service.reject_card(card_id)
    assert rejected_dto.status == "rejected"
