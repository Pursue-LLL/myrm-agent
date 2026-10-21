"""Tests for `router_stream_throttle` (correctness + wall-time regression ceiling)."""

from __future__ import annotations

import time

import pytest

from app.channels.routing.router_stream_throttle import (
    should_skip_throttled_placeholder_edit,
)


def test_initial_last_edit_never_blocks_first_edit() -> None:
    """With `last_edit_at == 0.0`, elapsed time is large for any realistic `now`, so the guard allows edit."""
    now = 1_000_000.0
    assert should_skip_throttled_placeholder_edit(now, 0.0, 0.25) is False


def test_within_interval_skips() -> None:
    assert should_skip_throttled_placeholder_edit(100.05, 100.0, 0.25) is True


def test_exact_interval_allows_edit() -> None:
    """Elapsed == min_interval is not skipped (strict <)."""
    assert should_skip_throttled_placeholder_edit(101.0, 100.0, 1.0) is False


def test_same_clock_skips_when_interval_positive() -> None:
    assert should_skip_throttled_placeholder_edit(50.0, 50.0, 0.1) is True


@pytest.mark.benchmark
def test_throttle_guard_wall_time_ceiling() -> None:
    """Many iterations must finish within a loose wall-time bound; on failure the message includes measured ops/s.

    This is a regression guard, not a claim of speedup versus another implementation.
    """
    n = 100_000
    # Fixed clocks: 0.1s elapsed < 0.5s interval => skip branch on every iteration.
    now, last, interval = 1_000_000.0, 999_999.9, 0.5
    t0 = time.perf_counter()
    hits = 0
    for _ in range(n):
        if should_skip_throttled_placeholder_edit(now, last, interval):
            hits += 1
    elapsed = time.perf_counter() - t0
    assert hits == n
    ops = n / elapsed if elapsed > 0 else 0.0
    assert elapsed < 1.0, f"expected {n} throttle checks <1s wall time, got {elapsed:.4f}s (~{ops:.0f} ops/s)"
