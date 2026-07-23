"""Unit tests for desktop approval E2E wall-clock fail-fast."""

from __future__ import annotations

import time

import pytest

from tests.e2e.desktop_approval.constants import (
    DESKTOP_E2E_WALL_CLOCK_FAIL_SEC,
    assert_desktop_e2e_wall_clock,
)


def test_wall_clock_fail_fast_triggers_after_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.constants.DESKTOP_E2E_WALL_CLOCK_FAIL_SEC",
        0.05,
    )
    started = time.monotonic() - 0.1
    with pytest.raises(AssertionError, match="wall-clock fail-fast"):
        assert_desktop_e2e_wall_clock(started, phase="unit-test")


def test_wall_clock_within_budget_passes() -> None:
    assert_desktop_e2e_wall_clock(time.monotonic(), phase="unit-test")
    assert DESKTOP_E2E_WALL_CLOCK_FAIL_SEC == 600.0
