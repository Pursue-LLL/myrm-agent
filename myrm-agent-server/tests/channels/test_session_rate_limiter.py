"""Unit tests for SessionRateLimiter."""

from __future__ import annotations

import time

import pytest

from app.channels.routing.session_rate_limiter import SessionRateLimiter


class TestSessionRateLimiter:
    """Test suite for SessionRateLimiter."""

    def test_allows_updates_under_limit(self) -> None:
        """Allows updates when under rate limit."""
        limiter = SessionRateLimiter(max_updates_per_minute=5)

        for _ in range(5):
            assert limiter.can_update("session-1")
            limiter.record_update("session-1")

        assert limiter.get_update_count("session-1") == 5

    def test_blocks_updates_over_limit(self) -> None:
        """Blocks updates when rate limit exceeded."""
        limiter = SessionRateLimiter(max_updates_per_minute=3)

        for _ in range(3):
            limiter.record_update("session-1")

        assert not limiter.can_update("session-1")
        assert limiter.get_update_count("session-1") == 3

    def test_separate_sessions_independent(self) -> None:
        """Different sessions have independent rate limits."""
        limiter = SessionRateLimiter(max_updates_per_minute=2)

        limiter.record_update("session-1")
        limiter.record_update("session-1")

        assert not limiter.can_update("session-1")
        assert limiter.can_update("session-2")

    def test_sliding_window_cleanup(self) -> None:
        """Old updates are cleaned up after window expires."""
        limiter = SessionRateLimiter(max_updates_per_minute=2, window_seconds=0.1)

        limiter.record_update("session-1")
        limiter.record_update("session-1")

        assert not limiter.can_update("session-1")

        time.sleep(0.15)

        assert limiter.can_update("session-1")
        assert limiter.get_update_count("session-1") == 0

    def test_manual_reset(self) -> None:
        """Manual reset clears session rate limit."""
        limiter = SessionRateLimiter(max_updates_per_minute=2)

        limiter.record_update("session-1")
        limiter.record_update("session-1")
        assert not limiter.can_update("session-1")

        limiter.reset("session-1")
        assert limiter.can_update("session-1")

    def test_zero_count_for_unknown_session(self) -> None:
        """Unknown session returns zero count."""
        limiter = SessionRateLimiter()
        assert limiter.get_update_count("unknown") == 0
        assert limiter.can_update("unknown")


@pytest.mark.benchmark(group="rate_limiter")
def test_benchmark_can_update(benchmark: pytest.fixture) -> None:
    """Benchmark rate limit check performance."""
    limiter = SessionRateLimiter()
    limiter.record_update("session-1")

    def check() -> bool:
        return limiter.can_update("session-1")

    result = benchmark(check)
    assert result is True


@pytest.mark.benchmark(group="rate_limiter")
def test_benchmark_record_update(benchmark: pytest.fixture) -> None:
    """Benchmark update recording performance."""
    limiter = SessionRateLimiter()

    def record() -> None:
        limiter.record_update("session-1")

    benchmark(record)


@pytest.mark.benchmark(group="rate_limiter")
def test_benchmark_get_count(benchmark: pytest.fixture) -> None:
    """Benchmark count retrieval performance."""
    limiter = SessionRateLimiter()
    for _ in range(10):
        limiter.record_update("session-1")

    def get_count() -> int:
        return limiter.get_update_count("session-1")

    result = benchmark(get_count)
    assert result == 10
