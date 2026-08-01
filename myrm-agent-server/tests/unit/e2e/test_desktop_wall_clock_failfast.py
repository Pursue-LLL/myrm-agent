"""Unit tests for desktop approval E2E wall-clock fail-fast."""

from __future__ import annotations

import time

import pytest

from tests.e2e.desktop_approval.constants import (
    DESKTOP_E2E_WALL_CLOCK_FAIL_SEC,
    assert_desktop_e2e_wall_clock,
)


def test_wall_clock_fail_fast_triggers_after_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.constants._resolve_desktop_e2e_wall_clock_fail_sec",
        lambda: 0.05,
    )
    started = time.monotonic() - 0.1
    with pytest.raises(AssertionError, match="wall-clock fail-fast"):
        assert_desktop_e2e_wall_clock(started, phase="unit-test")


def test_wall_clock_within_budget_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("E2E_SIGNOFF", raising=False)
    assert_desktop_e2e_wall_clock(time.monotonic(), phase="unit-test")
    assert DESKTOP_E2E_WALL_CLOCK_FAIL_SEC == 200.0


def test_signoff_wall_clock_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("E2E_SIGNOFF", "1")
    from tests.e2e.desktop_approval import constants as mod

    assert mod._resolve_desktop_e2e_wall_clock_fail_sec() == 280.0


def test_signoff_desktop_soak_wall_clock_scales(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("E2E_SIGNOFF", "1")
    monkeypatch.setenv("MYRM_E2E_DESKTOP_SOAK", "1")
    from unittest.mock import patch

    from tests.e2e.desktop_approval import constants as mod

    with patch(
        "cdp_chat_support.signoff_parallel_desktop_wall_clock_fail_sec",
        return_value=525.0,
    ):
        assert mod._resolve_desktop_e2e_wall_clock_fail_sec() == 525.0
