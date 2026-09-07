"""Unit tests for TroubleshootingBudgetManager in app.channels.delegation.

Tests budget decrement, strategy classification, oscillation prevention,
high-risk command interception, and approval escalation upon budget exhaustion.
"""

from __future__ import annotations

import pytest

from app.channels.delegation.delegation_troubleshoot import (
    TroubleshootDecision,
    TroubleshootStrategyType,
    TroubleshootingBudgetManager,
)


def test_troubleshoot_budget_initial_state() -> None:
    mgr = TroubleshootingBudgetManager(default_max_budget=5)
    assert mgr.get_remaining_budget("task-123") == 5


def test_troubleshoot_network_mirror_classification() -> None:
    mgr = TroubleshootingBudgetManager(default_max_budget=3)
    error = "npm ERR! code ETIMEDOUT\nnpm ERR! syscall connect\nnpm ERR! errno ETIMEDOUT\nnpm ERR! network request to https://registry.npmjs.org/express failed"

    dec = mgr.evaluate_and_consume("task-net", error, proposed_action="npm install")
    assert dec.should_retry is True
    assert dec.strategy == TroubleshootStrategyType.MIRROR_FALLBACK
    assert dec.remaining_budget == 2
    assert dec.attempt_count == 1
    assert "mirror" in dec.beacon_message.lower()


def test_troubleshoot_port_collision_classification() -> None:
    mgr = TroubleshootingBudgetManager(default_max_budget=3)
    error = "Error: listen EADDRINUSE: address already in use :::8000"

    dec = mgr.evaluate_and_consume("task-port", error, proposed_action="python -m uvicorn app:app --port 8000")
    assert dec.should_retry is True
    assert dec.strategy == TroubleshootStrategyType.PORT_REBIND
    assert "port" in dec.remediation_hint.lower()


def test_troubleshoot_high_risk_interception() -> None:
    mgr = TroubleshootingBudgetManager(default_max_budget=5)
    danger_cmd = "rm -rf / --no-preserve-root"

    dec = mgr.evaluate_and_consume("task-sec", "Permission error", proposed_action=danger_cmd)
    assert dec.should_retry is False
    assert dec.requires_human_approval is True
    assert "Dangerous command intercepted" in dec.approval_reason


def test_troubleshoot_budget_exhaustion_escalation() -> None:
    mgr = TroubleshootingBudgetManager(default_max_budget=2)

    # 1st attempt
    dec1 = mgr.evaluate_and_consume("task-ex", "Error 1", proposed_action="retry 1")
    assert dec1.should_retry is True
    assert dec1.remaining_budget == 1

    # 2nd attempt
    dec2 = mgr.evaluate_and_consume("task-ex", "Error 2", proposed_action="retry 2")
    assert dec2.should_retry is True
    assert dec2.remaining_budget == 0

    # 3rd attempt (exceeded budget)
    dec3 = mgr.evaluate_and_consume("task-ex", "Error 3", proposed_action="retry 3")
    assert dec3.should_retry is False
    assert dec3.requires_human_approval is True
    assert "Exhausted 2 autonomous" in dec3.approval_reason


def test_troubleshoot_reset_task() -> None:
    mgr = TroubleshootingBudgetManager(default_max_budget=3)
    mgr.evaluate_and_consume("task-rst", "Error")
    assert mgr.get_remaining_budget("task-rst") == 2

    mgr.reset_task("task-rst")
    assert mgr.get_remaining_budget("task-rst") == 3
