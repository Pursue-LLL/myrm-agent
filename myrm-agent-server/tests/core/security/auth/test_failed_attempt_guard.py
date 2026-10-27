"""Tests for FailedAttemptGuard (brute-force lockout with a bounded key set)."""

import pytest

from app.core.security.auth.failed_attempt_guard import FailedAttemptGuard


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


@pytest.fixture
def guard(clock: _Clock) -> FailedAttemptGuard:
    return FailedAttemptGuard(max_failures=5, window_seconds=60.0, max_keys=8, clock=clock)


def _fail(guard: FailedAttemptGuard, key: str, times: int) -> None:
    for _ in range(times):
        guard.record_failure(key)


def test_unknown_key_is_not_locked(guard: FailedAttemptGuard) -> None:
    assert guard.retry_after("k") is None


def test_locks_at_the_failure_limit_and_reports_remaining_window(guard: FailedAttemptGuard, clock: _Clock) -> None:
    _fail(guard, "k", 4)
    assert guard.retry_after("k") is None

    guard.record_failure("k")
    assert guard.retry_after("k") == 60

    clock.now += 25
    assert guard.retry_after("k") == 35


def test_lock_never_reports_less_than_one_second(guard: FailedAttemptGuard, clock: _Clock) -> None:
    _fail(guard, "k", 5)
    clock.now += 59.9
    assert guard.retry_after("k") == 1


def test_lock_lifts_when_the_window_expires(guard: FailedAttemptGuard, clock: _Clock) -> None:
    _fail(guard, "k", 5)
    clock.now += 60
    assert guard.retry_after("k") is None


def test_failures_age_out_individually(guard: FailedAttemptGuard, clock: _Clock) -> None:
    _fail(guard, "k", 3)
    clock.now += 40
    _fail(guard, "k", 2)
    assert guard.retry_after("k") == 20

    clock.now += 20  # the first three failures leave the window; two remain
    assert guard.retry_after("k") is None


def test_keys_are_independent(guard: FailedAttemptGuard) -> None:
    _fail(guard, "token-a:1.2.3.4", 5)
    assert guard.retry_after("token-a:1.2.3.4") == 60
    assert guard.retry_after("token-a:9.9.9.9") is None
    assert guard.retry_after("token-b:1.2.3.4") is None


def test_clear_resets_the_counter(guard: FailedAttemptGuard) -> None:
    _fail(guard, "k", 4)
    guard.clear("k")
    _fail(guard, "k", 4)
    assert guard.retry_after("k") is None


def test_clear_unlocks_a_locked_key(guard: FailedAttemptGuard) -> None:
    _fail(guard, "k", 5)
    guard.clear("k")
    assert guard.retry_after("k") is None


def test_clear_unknown_key_is_a_noop(guard: FailedAttemptGuard) -> None:
    guard.clear("never-seen")


def test_tracked_keys_are_bounded_and_evict_the_least_recently_failed(guard: FailedAttemptGuard) -> None:
    for i in range(100):
        guard.record_failure(f"garbage-{i}")

    assert len(guard._failures) == 8
    assert list(guard._failures) == [f"garbage-{i}" for i in range(92, 100)]


def test_flooding_distinct_keys_can_flush_a_locked_key(guard: FailedAttemptGuard) -> None:
    """Documents the bounded-memory trade-off: an attacker needs max_keys extra requests per flush."""
    _fail(guard, "victim", 5)
    for i in range(8):
        guard.record_failure(f"garbage-{i}")
    assert guard.retry_after("victim") is None


def test_expired_keys_are_dropped_when_queried(guard: FailedAttemptGuard, clock: _Clock) -> None:
    _fail(guard, "k", 2)
    clock.now += 61
    assert guard.retry_after("k") is None
    assert "k" not in guard._failures


def test_stored_failures_per_key_are_capped(guard: FailedAttemptGuard) -> None:
    _fail(guard, "k", 50)
    assert len(guard._failures["k"]) == 5


@pytest.mark.parametrize(
    "kwargs",
    [{"max_failures": 0}, {"window_seconds": 0}, {"window_seconds": -1}, {"max_keys": 0}],
)
def test_rejects_invalid_configuration(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="must be"):
        FailedAttemptGuard(**kwargs)  # type: ignore[arg-type]
