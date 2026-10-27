"""Scheduled remote backup rules: the user's interval, when a backup is due, when to tell the user.

[INPUT]
app.services.memory.backup.remote_sync.schedule::interval_minutes/is_due/should_alert
app.services.memory.backup.remote_sync.state::RemoteSyncState

[OUTPUT]
Which interval is honoured, which moments start a backup, and which failure streaks raise an alert.

[POS]
Pure rule tests with an explicit clock; no I/O.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.memory.backup.remote_sync.schedule import (
    ALERT_AFTER_FAILURES,
    DEFAULT_INTERVAL_MINUTES,
    MAX_INTERVAL_MINUTES,
    MIN_INTERVAL_MINUTES,
    interval_minutes,
    is_due,
    should_alert,
)
from app.services.memory.backup.remote_sync.state import RemoteSyncState

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
DAY = 1440


def _succeeded(ago: timedelta) -> RemoteSyncState:
    return RemoteSyncState(last_success_at=NOW - ago, last_attempt_at=NOW - ago)


def _failing(failures: int, *, last_success_ago: timedelta | None, alerted: bool = False) -> RemoteSyncState:
    return RemoteSyncState(
        last_success_at=None if last_success_ago is None else NOW - last_success_ago,
        last_attempt_at=NOW,
        last_error_code="upload",
        consecutive_failures=failures,
        alerted=alerted,
    )


def test_the_supported_interval_range_is_one_tick_to_one_day() -> None:
    assert (MIN_INTERVAL_MINUTES, MAX_INTERVAL_MINUTES, DEFAULT_INTERVAL_MINUTES) == (60, 1440, 1440)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, DAY),
        ("60", DAY),
        (True, DAY),
        (1.5, DAY),
        (60, 60),
        (360, 360),
        (DAY, DAY),
        (5, 60),
        (0, 60),
        (-10, 60),
        (10_080, DAY),
    ],
)
def test_the_stored_interval_is_honoured_and_anything_unusable_falls_back_into_range(raw: object, expected: int) -> None:
    assert interval_minutes(raw) == expected


def test_a_backup_is_due_when_none_was_ever_recorded() -> None:
    assert is_due(RemoteSyncState(), DAY, NOW) is True


def test_a_backup_is_not_due_before_the_interval_has_passed() -> None:
    assert is_due(_succeeded(timedelta(hours=23)), DAY, NOW) is False
    assert is_due(_succeeded(timedelta(minutes=30)), 60, NOW) is False


def test_a_backup_is_due_once_the_interval_has_passed() -> None:
    assert is_due(_succeeded(timedelta(hours=24)), DAY, NOW) is True
    assert is_due(_succeeded(timedelta(days=9)), DAY, NOW) is True


def test_a_few_minutes_of_tick_jitter_do_not_push_a_backup_a_whole_tick_later() -> None:
    assert is_due(_succeeded(timedelta(hours=24) - timedelta(minutes=3)), DAY, NOW) is True
    assert is_due(_succeeded(timedelta(hours=24) - timedelta(minutes=10)), DAY, NOW) is False


def test_a_success_dated_in_the_future_proves_nothing_and_does_not_stop_the_schedule() -> None:
    # A clock that ran ahead and was corrected: waiting for the clock to catch up would stop backups for as long as it was off.
    assert is_due(_succeeded(timedelta(hours=-5)), DAY, NOW) is True


def test_a_failed_attempt_is_retried_at_the_next_tick_because_only_a_success_resets_the_clock() -> None:
    state = _failing(1, last_success_ago=timedelta(hours=25))
    assert is_due(state, DAY, NOW) is True


def test_one_failure_does_not_alert() -> None:
    assert ALERT_AFTER_FAILURES == 2
    assert should_alert(_failing(1, last_success_ago=None), DAY, NOW) is False


def test_repeated_failures_without_any_success_alert() -> None:
    assert should_alert(_failing(2, last_success_ago=None), DAY, NOW) is True


def test_repeated_failures_alert_once_the_last_success_is_more_than_two_intervals_old() -> None:
    assert should_alert(_failing(2, last_success_ago=timedelta(hours=49)), DAY, NOW) is True


def test_repeated_failures_stay_quiet_while_the_last_success_is_recent_enough_to_be_a_short_outage() -> None:
    # A laptop offline for a day: the previous backup still protects the data, nobody needs to be woken.
    assert should_alert(_failing(5, last_success_ago=timedelta(hours=30)), DAY, NOW) is False
    assert should_alert(_failing(3, last_success_ago=timedelta(hours=3)), 60, NOW) is True


def test_a_failure_streak_alerts_only_once() -> None:
    assert should_alert(_failing(9, last_success_ago=None, alerted=True), DAY, NOW) is False


def test_a_success_dated_in_the_future_counts_as_no_success_for_the_alert() -> None:
    assert should_alert(_failing(2, last_success_ago=timedelta(hours=-5)), DAY, NOW) is True
