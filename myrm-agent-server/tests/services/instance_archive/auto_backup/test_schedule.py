"""When a scheduled backup is due and when the user is told it is late."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.instance_archive.auto_backup.models import AutoBackupSettings, AutoBackupState, Frequency
from app.services.instance_archive.auto_backup.schedule import is_due, is_overdue, reference_moment

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
ON = AutoBackupSettings(enabled=True)
WEEKLY = AutoBackupSettings(enabled=True, frequency=Frequency.WEEKLY)
NEVER = AutoBackupState()


def _ago(delta: timedelta) -> datetime:
    return NOW - delta


def _failed(*, attempt_ago: timedelta, failures: int) -> AutoBackupState:
    return AutoBackupState(last_attempt_at=NOW - attempt_ago, consecutive_failures=failures)


def test_disabled_is_never_due_or_overdue() -> None:
    off = AutoBackupSettings(enabled=False)
    assert not is_due(off, NEVER, None, NOW)
    assert not is_overdue(off, _failed(attempt_ago=timedelta(minutes=5), failures=5), _ago(timedelta(days=90)), NOW)


def test_a_folder_without_a_backup_is_due_immediately() -> None:
    assert is_due(ON, NEVER, None, NOW)


def test_due_follows_the_newest_backup_in_the_folder_and_the_frequency() -> None:
    assert not is_due(ON, NEVER, _ago(timedelta(hours=23)), NOW)
    assert is_due(ON, NEVER, _ago(timedelta(hours=24)), NOW)
    assert not is_due(WEEKLY, NEVER, _ago(timedelta(days=6)), NOW)
    assert is_due(WEEKLY, NEVER, _ago(timedelta(days=7)), NOW)


def test_a_run_missed_while_closed_is_made_up_at_the_next_tick() -> None:
    assert is_due(ON, NEVER, _ago(timedelta(days=11)), NOW)


def test_failures_retry_soon_then_back_off_to_the_frequency() -> None:
    old = _ago(timedelta(days=2))
    assert not is_due(ON, _failed(attempt_ago=timedelta(minutes=10), failures=1), old, NOW)
    assert is_due(ON, _failed(attempt_ago=timedelta(minutes=45), failures=2), old, NOW)
    assert not is_due(ON, _failed(attempt_ago=timedelta(hours=5), failures=3), old, NOW)
    assert is_due(ON, _failed(attempt_ago=timedelta(hours=25), failures=3), old, NOW)


@pytest.mark.parametrize("failures", [1, 3])
@pytest.mark.parametrize("ahead", [timedelta(hours=8), timedelta(days=3), timedelta(days=400)])
def test_a_failed_attempt_dated_after_now_does_not_hold_back_the_retry(ahead: timedelta, failures: int) -> None:
    # Stamped by a clock that ran ahead and was corrected since: no back-off has actually been served.
    assert is_due(ON, _failed(attempt_ago=-ahead, failures=failures), None, NOW)


def test_an_attempt_made_this_very_moment_still_backs_off() -> None:
    assert not is_due(ON, _failed(attempt_ago=timedelta(0), failures=1), None, NOW)


def test_overdue_means_twice_the_frequency_without_a_backup() -> None:
    assert not is_overdue(ON, NEVER, _ago(timedelta(hours=47)), NOW)
    assert is_overdue(ON, NEVER, _ago(timedelta(hours=49)), NOW)
    assert not is_overdue(WEEKLY, NEVER, _ago(timedelta(days=13)), NOW)
    assert is_overdue(WEEKLY, NEVER, _ago(timedelta(days=15)), NOW)


def test_a_folder_without_a_backup_is_overdue_only_after_an_attempt_failed() -> None:
    assert not is_overdue(ON, NEVER, None, NOW)
    assert is_overdue(ON, _failed(attempt_ago=timedelta(minutes=5), failures=1), None, NOW)


def test_a_readable_folder_is_the_reference_even_when_it_is_empty() -> None:
    attempted = AutoBackupState(last_attempt_at=_ago(timedelta(hours=1)))

    assert reference_moment(_ago(timedelta(hours=5)), True, attempted, NOW) == _ago(timedelta(hours=5))
    assert reference_moment(None, True, attempted, NOW) is None  # emptied by hand: due at once


def test_an_unreadable_folder_after_a_good_attempt_is_measured_from_that_attempt() -> None:
    attempted = AutoBackupState(last_attempt_at=_ago(timedelta(hours=2)))
    reference = reference_moment(None, False, attempted, NOW)

    assert reference == _ago(timedelta(hours=2))
    assert not is_due(ON, attempted, reference, NOW)  # taking the drive away is not a missed backup
    assert is_due(ON, attempted, reference, NOW + timedelta(hours=22))


def test_an_unreadable_folder_with_nothing_to_stand_on_is_unknown() -> None:
    failing = _failed(attempt_ago=timedelta(minutes=45), failures=2)

    assert reference_moment(None, False, NEVER, NOW) is None
    assert reference_moment(None, False, failing, NOW) is None
    assert is_due(ON, failing, None, NOW)  # the retry back-off still decides when to try again


def test_an_attempt_dated_after_now_stands_in_for_nothing() -> None:
    ahead = AutoBackupState(last_attempt_at=NOW + timedelta(hours=8))
    five_hours_ago = _ago(timedelta(hours=5))

    assert reference_moment(None, False, ahead, NOW) is None
    assert is_due(ON, ahead, None, NOW)  # unknown folder, nothing trustworthy to measure from: try, and learn
    assert reference_moment(five_hours_ago, True, ahead, NOW) == five_hours_ago  # a readable folder needs none
