"""The pinned host clock reads eight hours ahead of UTC inside, the host's own zone outside, and raises when it did not take."""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta

import pytest

from tests.support.host_clock import pin_host_clock_to_utc_plus_8

_PLUS_EIGHT = timedelta(hours=8)
_needs_tzset = pytest.mark.skipif(
    not hasattr(time, "tzset"), reason="the process clock moves only where time.tzset exists"
)


def _clock_offset() -> timedelta | None:
    return datetime(2026, 1, 1).astimezone().utcoffset()


@_needs_tzset
def test_inside_the_pin_the_process_clock_is_eight_hours_ahead_of_utc() -> None:
    with pin_host_clock_to_utc_plus_8():
        assert _clock_offset() == _PLUS_EIGHT
        assert time.localtime(0).tm_gmtoff == _PLUS_EIGHT.total_seconds()


@_needs_tzset
def test_the_host_zone_is_back_after_the_pin_even_when_the_block_raises() -> None:
    zone_variable, host_offset = os.environ.get("TZ"), _clock_offset()

    with pytest.raises(ZeroDivisionError), pin_host_clock_to_utc_plus_8():
        raise ZeroDivisionError

    assert os.environ.get("TZ") == zone_variable
    assert _clock_offset() == host_offset


@_needs_tzset
def test_a_pin_that_did_not_take_raises_instead_of_letting_the_test_run_unpinned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ClockAtUtc:
        tm_gmtoff = 0

    zone_variable, host_offset = os.environ.get("TZ"), _clock_offset()
    monkeypatch.setattr(time, "localtime", lambda *_seconds: _ClockAtUtc())

    with pytest.raises(RuntimeError, match="eight hours ahead"), pin_host_clock_to_utc_plus_8():
        pytest.fail("the block of a pin that did not take must not run")

    assert os.environ.get("TZ") == zone_variable
    assert _clock_offset() == host_offset


def test_without_time_tzset_the_pin_leaves_the_clock_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    zone_variable, host_offset = os.environ.get("TZ"), _clock_offset()
    monkeypatch.delattr(time, "tzset", raising=False)

    with pin_host_clock_to_utc_plus_8():
        assert os.environ.get("TZ") == zone_variable
        assert _clock_offset() == host_offset
