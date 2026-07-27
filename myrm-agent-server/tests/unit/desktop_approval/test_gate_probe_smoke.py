"""Unit smoke tests for desktop approval gate probe helpers."""

from __future__ import annotations

import pytest

from tests.e2e.desktop_approval.gate_probe import (
    _DesktopFallbackBudget,
    _record_pending_seed_fallback,
    _record_synthetic_dref_fallback,
    interact_without_gate_handoff_elapsed,
    require_approval_gate_triggered,
    snapshot_loop_stuck_sec,
)


def test_require_approval_gate_triggered_passes_when_pending() -> None:
    require_approval_gate_triggered(
        last_tool="",
        server_pending=1,
        ui_pending=False,
    )


def test_require_approval_gate_triggered_fails_when_idle() -> None:
    with pytest.raises(AssertionError, match="snapshot/vision loop"):
        require_approval_gate_triggered(
            last_tool="desktop_snapshot_tool",
            server_pending=0,
            ui_pending=False,
            provider_hint=" provider.is_ready=True",
        )


def test_require_approval_gate_triggered_fails_when_unknown_tool() -> None:
    with pytest.raises(AssertionError, match="never triggered desktop approval gate"):
        require_approval_gate_triggered(
            last_tool="web_search_tool",
            server_pending=0,
            ui_pending=False,
        )


def test_snapshot_loop_stuck_sec_tracks_snapshot_without_gate() -> None:
    assert (
        snapshot_loop_stuck_sec(
            last_tool="desktop_snapshot_tool",
            server_pending=0,
            ui_pending=False,
            loop_started_at=None,
        )
        == 0.0
    )
    started = 100.0
    assert (
        snapshot_loop_stuck_sec(
            last_tool="desktop_snapshot_tool",
            server_pending=0,
            ui_pending=False,
            loop_started_at=started,
            now=150.0,
        )
        == 50.0
    )
    assert (
        snapshot_loop_stuck_sec(
            last_tool="desktop_snapshot_tool",
            server_pending=1,
            ui_pending=False,
            loop_started_at=started,
            now=150.0,
        )
        is None
    )


def test_interact_without_gate_handoff_elapsed_requires_interact_seen() -> None:
    assert (
        interact_without_gate_handoff_elapsed(
            interact_seen_at=None,
            server_pending=0,
            ui_pending=False,
            now=50.0,
            handoff_sec=10.0,
        )
        is False
    )


def test_interact_without_gate_handoff_elapsed_respects_pending_gate() -> None:
    assert (
        interact_without_gate_handoff_elapsed(
            interact_seen_at=10.0,
            server_pending=1,
            ui_pending=False,
            now=30.0,
            handoff_sec=10.0,
        )
        is False
    )
    assert (
        interact_without_gate_handoff_elapsed(
            interact_seen_at=10.0,
            server_pending=0,
            ui_pending=True,
            now=30.0,
            handoff_sec=10.0,
        )
        is False
    )


def test_interact_without_gate_handoff_elapsed_after_threshold() -> None:
    assert (
        interact_without_gate_handoff_elapsed(
            interact_seen_at=10.0,
            server_pending=0,
            ui_pending=False,
            now=19.9,
            handoff_sec=10.0,
        )
        is False
    )
    assert (
        interact_without_gate_handoff_elapsed(
            interact_seen_at=10.0,
            server_pending=0,
            ui_pending=False,
            now=20.0,
            handoff_sec=10.0,
        )
        is True
    )


def test_record_synthetic_dref_fallback_raises_when_budget_exceeded() -> None:
    budget = _DesktopFallbackBudget(synthetic_dref_limit=0, pending_seed_limit=1)
    with pytest.raises(AssertionError, match="synthetic dref fallback budget exceeded"):
        _record_synthetic_dref_fallback(budget, reason="unit-test")


def test_record_pending_seed_fallback_tracks_usage_within_budget() -> None:
    budget = _DesktopFallbackBudget(synthetic_dref_limit=1, pending_seed_limit=2)
    _record_pending_seed_fallback(budget, reason="unit-test", request_id="req-1")
    _record_pending_seed_fallback(budget, reason="unit-test", request_id="req-2")
    assert budget.pending_seed_used == 2


def test_record_pending_seed_fallback_raises_when_budget_exceeded() -> None:
    budget = _DesktopFallbackBudget(synthetic_dref_limit=1, pending_seed_limit=1)
    _record_pending_seed_fallback(budget, reason="unit-test", request_id="req-1")
    with pytest.raises(AssertionError, match="pending seed fallback budget exceeded"):
        _record_pending_seed_fallback(budget, reason="unit-test", request_id="req-2")
