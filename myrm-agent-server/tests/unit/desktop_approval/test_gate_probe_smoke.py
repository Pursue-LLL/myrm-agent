"""Unit smoke tests for desktop approval gate probe helpers."""

from __future__ import annotations

import pytest

from tests.e2e.desktop_approval.gate_probe import require_approval_gate_triggered


def test_require_approval_gate_triggered_passes_when_pending() -> None:
    require_approval_gate_triggered(
        last_tool="",
        server_pending=1,
        ui_pending=False,
    )


def test_require_approval_gate_triggered_fails_when_idle() -> None:
    with pytest.raises(AssertionError, match="never triggered desktop approval gate"):
        require_approval_gate_triggered(
            last_tool="desktop_snapshot_tool",
            server_pending=0,
            ui_pending=False,
            provider_hint=" provider.is_ready=True",
        )
