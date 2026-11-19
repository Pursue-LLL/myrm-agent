"""Financial spend calls always wait for a human, in auto mode and under a blanket allow rule.

Verifies:
1. The auto-mode reviewer never auto-approves a financial spend call (it is skipped, the call goes to the human).
2. A rule that allows every MCP tool does not let a financial spend call through.
3. Calls that are not financial keep their auto-mode and rule behavior.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import ToolCall

import myrm_agent_harness.agent.security.approval_flow as approval_flow
from myrm_agent_harness.agent.middlewares.approval._interrupt_payload import build_interrupt_payload
from myrm_agent_harness.agent.middlewares.approval.batch_processor import evaluate_tool_batch
from myrm_agent_harness.agent.middlewares.approval.helpers import reset_denial_counter
from myrm_agent_harness.agent.security.audit import get_audit_entries, reset_audit_log
from myrm_agent_harness.agent.security.types import (
    PermissionAction,
    PermissionRule,
    ReviewDecision,
    ReviewResult,
    SecurityConfig,
)

_REVIEWER = "myrm_agent_harness.agent.middlewares.approval._batch_review._security_reviewer"


@pytest.fixture(autouse=True)
def _clean_state() -> Iterator[None]:
    reset_denial_counter()
    reset_audit_log()
    approval_flow._allowlist = approval_flow.Allowlist()
    yield
    reset_audit_log()


def _charge_call(tc_id: str = "tc_charge") -> ToolCall:
    return ToolCall(
        type="tool_call",
        name="stripe_create_charge",
        args={"amount": 2500, "currency": "USD", "recipient": "acct_winner"},
        id=tc_id,
    )


def _weather_call() -> ToolCall:
    return ToolCall(type="tool_call", name="mcp__weather__get_forecast", args={"city": "Oslo"}, id="tc_weather")


def _allow_reviewer() -> AsyncMock:
    reviewer = AsyncMock()
    reviewer.review = AsyncMock(
        return_value=ReviewResult(decision=ReviewDecision.ALLOW, reason="the user asked for this payment")
    )
    return reviewer


async def _evaluate(config: SecurityConfig, call: ToolCall, session_key: str) -> tuple[list, list, list]:
    return await evaluate_tool_batch(
        [call],
        config,
        is_cron=False,
        workspace_root="/tmp",
        session_key=session_key,
        args_hashes={},
        is_interactive=True,
    )


@pytest.mark.asyncio
async def test_auto_mode_reviewer_does_not_auto_approve_a_spend_call() -> None:
    reviewer = _allow_reviewer()

    with patch(_REVIEWER, reviewer):
        approved, denied, pending = await _evaluate(SecurityConfig(auto_mode_enabled=True), _charge_call(), "fin1")

    assert (len(approved), len(denied), len(pending)) == (0, 0, 1)
    reviewer.review.assert_not_awaited()
    _idx, _tc, _perm, _reason, extra_ctx = pending[0]
    assert extra_ctx["is_spend"] is True
    assert extra_ctx["spend_amount"] == 2500
    assert extra_ctx["high_risk"] is True
    assert extra_ctx["hide_allow_always"] is True
    assert extra_ctx["action_digest"]


@pytest.mark.asyncio
async def test_spend_call_in_auto_mode_reaches_the_card_as_a_spend_request() -> None:
    with patch(_REVIEWER, _allow_reviewer()):
        _approved, _denied, pending = await _evaluate(SecurityConfig(auto_mode_enabled=True), _charge_call(), "fin2")

    payload, _indices = build_interrupt_payload(
        pending_approval=pending, session_key="fin2", approval_timeout_seconds=120
    )

    review_config = payload["reviewConfigs"][0]
    assert review_config["isSpend"] is True
    assert review_config["spendAmount"] == 2500
    assert review_config["spendCurrency"] == "USD"
    assert review_config["hideAllowAlways"] is True


@pytest.mark.asyncio
async def test_blanket_mcp_allow_rule_does_not_pass_a_spend_call() -> None:
    config = SecurityConfig(
        ruleset=(PermissionRule("mcp_invoke", "*", PermissionAction.ALLOW),),
        auto_mode_enabled=False,
    )

    approved, denied, pending = await _evaluate(config, _charge_call(), "fin3")

    assert (len(approved), len(denied), len(pending)) == (0, 0, 1)
    decisions = [entry.decision for entry in get_audit_entries()]
    assert "FINANCIAL_GATE_ESCALATED" in decisions
    assert pending[0][4]["is_spend"] is True


@pytest.mark.asyncio
async def test_non_spend_mcp_call_keeps_the_auto_mode_review() -> None:
    reviewer = _allow_reviewer()

    with patch(_REVIEWER, reviewer):
        approved, denied, pending = await _evaluate(SecurityConfig(auto_mode_enabled=True), _weather_call(), "fin4")

    assert (len(approved), len(denied), len(pending)) == (1, 0, 0)
    reviewer.review.assert_awaited_once()


@pytest.mark.asyncio
async def test_non_spend_mcp_call_keeps_the_blanket_allow_rule() -> None:
    config = SecurityConfig(
        ruleset=(PermissionRule("mcp_invoke", "*", PermissionAction.ALLOW),),
        auto_mode_enabled=False,
    )

    approved, denied, pending = await _evaluate(config, _weather_call(), "fin5")

    assert (len(approved), len(denied), len(pending)) == (1, 0, 0)
    assert "FINANCIAL_GATE_ESCALATED" not in [entry.decision for entry in get_audit_entries()]
