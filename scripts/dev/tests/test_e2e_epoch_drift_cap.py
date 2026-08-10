"""Unit tests for epoch drift attach cap scaling (§26.28 / R020).

Verifies that a SHARED attach under pending drift with active parallel leases
gets a scaled wait window (lease-aware retry/queue semantic) instead of the
fixed base cap, so deferred shared reloads never surface as false FAILs.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import e2e_api_verify as verify  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MYRM_E2E_EPOCH_DRIFT_ATTACH_CAP_SEC", raising=False)
    monkeypatch.delenv("MYRM_E2E_EPOCH_DRIFT_ATTACH_PER_LEASE_SEC", raising=False)


def test_no_drift_no_cap() -> None:
    assert (
        verify.epoch_drift_attach_cap_sec(
            blocked=False, epoch_match=True, drift_pending=False, active_leases=0
        )
        == 0
    )


def test_blocked_epoch_mismatch_base_cap() -> None:
    assert (
        verify.epoch_drift_attach_cap_sec(
            blocked=True, epoch_match=False, drift_pending=False, active_leases=0
        )
        == 120
    )


def test_blocked_epoch_match_returns_zero() -> None:
    """epoch_match means the backend serves the right source — no drift window."""
    assert (
        verify.epoch_drift_attach_cap_sec(
            blocked=True, epoch_match=True, drift_pending=True, active_leases=3
        )
        == 0
    )


def test_drift_pending_leases_scale_cap() -> None:
    """drift_pending + 2 active leases → base + 2*45, a bounded queue wait."""
    assert (
        verify.epoch_drift_attach_cap_sec(
            blocked=True, epoch_match=False, drift_pending=True, active_leases=2
        )
        == 120 + 2 * 45
    )


def test_drift_pending_zero_leases_uses_base() -> None:
    assert (
        verify.epoch_drift_attach_cap_sec(
            blocked=True, epoch_match=False, drift_pending=True, active_leases=0
        )
        == 120
    )


def test_cap_env_override() -> None:
    os.environ["MYRM_E2E_EPOCH_DRIFT_ATTACH_CAP_SEC"] = "30"
    os.environ["MYRM_E2E_EPOCH_DRIFT_ATTACH_PER_LEASE_SEC"] = "10"
    assert (
        verify.epoch_drift_attach_cap_sec(
            blocked=True, epoch_match=False, drift_pending=True, active_leases=3
        )
        == 30 + 3 * 10
    )


def test_non_numeric_env_ignored() -> None:
    os.environ["MYRM_E2E_EPOCH_DRIFT_ATTACH_CAP_SEC"] = "abc"
    os.environ["MYRM_E2E_EPOCH_DRIFT_ATTACH_PER_LEASE_SEC"] = "xyz"
    assert (
        verify.epoch_drift_attach_cap_sec(
            blocked=True, epoch_match=False, drift_pending=True, active_leases=4
        )
        == 120 + 4 * 45
    )


def test_negative_leases_use_base_cap() -> None:
    """Negative/zero lease counts fall through to the base cap, not the queue window."""
    assert (
        verify.epoch_drift_attach_cap_sec(
            blocked=True, epoch_match=False, drift_pending=True, active_leases=-1
        )
        == 120
    )
