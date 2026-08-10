"""R43: chrome_e2e pytest-timeout must cap per-item marks to lane SSOT (600s)."""

from __future__ import annotations

import pytest
from dev_gate_contract import (
    CHROME_E2E_DESKTOP_TIMEOUT_SECONDS,
    LIVE_CHROME_E2E_PYTEST_TIMEOUT_SEC,
    signoff_batch_pytest_timeout_ceiling_sec,
)

from tests.conftest import _apply_chrome_e2e_lane_timeout


class _TimeoutCapItem:
    def __init__(self) -> None:
        self.nodeid = "tests/support/test_chrome_e2e_timeout_cap.py::_TimeoutCapItem"
        self.own_markers = [
            pytest.mark.chrome_e2e(
                execution_mode="SHARED",
                access_scope="READ",
                workload="LIVE",
            ),
            pytest.mark.timeout(1800),
        ]

    def iter_markers(self, name: str | None = None):
        if name is None:
            yield from self.own_markers
            return
        for marker in self.own_markers:
            if marker.name == name:
                yield marker

    def add_marker(self, marker: pytest.Mark) -> None:
        self.own_markers.append(marker)

    def get_closest_marker(self, name: str) -> pytest.Mark | None:
        for marker in reversed(self.own_markers):
            if marker.name == name:
                return marker
        return None


def _pin_deterministic_lane_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin env so the floor computation is deterministic (no real lease/ramp load)."""
    monkeypatch.delenv("MYRM_E2E_EXECUTION_MODE", raising=False)
    monkeypatch.delenv("MYRM_E2E_PHASE_C_BURST_LANES", raising=False)
    monkeypatch.delenv("E2E_PARALLEL_RAMP_PYTEST_TIMEOUT_SEC", raising=False)
    monkeypatch.setattr(
        "stack_mutation_policy.wave_active_lease_count", lambda path: 0
    )


def test_r43_caps_high_desktop_timeout_mark_to_600(monkeypatch: pytest.MonkeyPatch) -> None:
    _pin_deterministic_lane_env(monkeypatch)
    item = _TimeoutCapItem()
    item.own_markers.append(pytest.mark.chrome_e2e_desktop)
    _apply_chrome_e2e_lane_timeout(item)
    timeout_marker = item.get_closest_marker("timeout")
    assert timeout_marker is not None
    assert int(timeout_marker.args[0]) == CHROME_E2E_DESKTOP_TIMEOUT_SECONDS


def test_r43_caps_takeover_live_timeout_mark_to_lane_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _pin_deterministic_lane_env(monkeypatch)
    item = _TimeoutCapItem()
    item.own_markers.append(pytest.mark.chrome_e2e_browser_takeover_live)
    _apply_chrome_e2e_lane_timeout(item)
    timeout_marker = item.get_closest_marker("timeout")
    assert timeout_marker is not None
    assert int(timeout_marker.args[0]) == LIVE_CHROME_E2E_PYTEST_TIMEOUT_SEC


def test_r43_signoff_batch_marker_raises_pytest_timeout_to_body_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("E2E_SIGNOFF", "1")
    item = _TimeoutCapItem()
    item.own_markers.append(pytest.mark.chrome_e2e_signoff_batch(body_sec=1200))
    _apply_chrome_e2e_lane_timeout(item)
    timeout_marker = item.get_closest_marker("timeout")
    assert timeout_marker is not None
    assert int(timeout_marker.args[0]) == signoff_batch_pytest_timeout_ceiling_sec(1200)
