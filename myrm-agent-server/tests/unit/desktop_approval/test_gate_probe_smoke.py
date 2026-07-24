"""Unit smoke tests for desktop approval gate probe helpers."""

from __future__ import annotations

import pytest

from tests.e2e.desktop_approval.gate_probe import (
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
