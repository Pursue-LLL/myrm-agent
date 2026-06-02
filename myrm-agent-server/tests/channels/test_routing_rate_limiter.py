"""SessionRateLimiter tests — sliding window, cleanup, reset."""

from __future__ import annotations

import time

from app.channels.routing.session_rate_limiter import (
    SessionRateLimiter,
)


class TestSessionRateLimiter:
    def test_defaults(self) -> None:
        limiter = SessionRateLimiter()
        assert limiter._max_updates == 60
        assert limiter._window_seconds == 60.0

    def test_can_update_empty(self) -> None:
        limiter = SessionRateLimiter(max_updates_per_minute=5)
        assert limiter.can_update("s1") is True

    def test_record_and_check(self) -> None:
        limiter = SessionRateLimiter(max_updates_per_minute=3)
        for _ in range(3):
            assert limiter.can_update("s1") is True
            limiter.record_update("s1")
        assert limiter.can_update("s1") is False

    def test_different_sessions_independent(self) -> None:
        limiter = SessionRateLimiter(max_updates_per_minute=2)
        limiter.record_update("s1")
        limiter.record_update("s1")
        assert limiter.can_update("s1") is False
        assert limiter.can_update("s2") is True

    def test_get_update_count(self) -> None:
        limiter = SessionRateLimiter()
        assert limiter.get_update_count("s1") == 0
        limiter.record_update("s1")
        limiter.record_update("s1")
        assert limiter.get_update_count("s1") == 2

    def test_reset(self) -> None:
        limiter = SessionRateLimiter(max_updates_per_minute=2)
        limiter.record_update("s1")
        limiter.record_update("s1")
        assert limiter.can_update("s1") is False
        limiter.reset("s1")
        assert limiter.can_update("s1") is True

    def test_reset_nonexistent(self) -> None:
        limiter = SessionRateLimiter()
        limiter.reset("nonexistent")

    def test_old_updates_cleaned(self) -> None:
        limiter = SessionRateLimiter(max_updates_per_minute=2, window_seconds=0.01)
        limiter.record_update("s1")
        limiter.record_update("s1")
        assert limiter.can_update("s1") is False

        time.sleep(0.02)
        assert limiter.can_update("s1") is True
        assert limiter.get_update_count("s1") == 0

    def test_cleanup_removes_empty_deque(self) -> None:
        limiter = SessionRateLimiter(max_updates_per_minute=5, window_seconds=0.01)
        limiter.record_update("s1")
        time.sleep(0.02)
        limiter._cleanup_old_updates("s1")
        assert "s1" not in limiter._session_updates

    def test_cleanup_no_session(self) -> None:
        limiter = SessionRateLimiter()
        limiter._cleanup_old_updates("nonexistent")
