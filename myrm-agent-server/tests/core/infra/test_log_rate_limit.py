"""Tests for LogStormFilter: bounded output, per-template suppression, and the disable switch."""

import logging

import pytest

from app.core.infra.log_rate_limit import LogStormFilter


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _record(message: str, *, level: int = logging.WARNING, name: str = "app.test") -> logging.LogRecord:
    return logging.LogRecord(name=name, level=level, pathname=__file__, lineno=1, msg=message, args=(), exc_info=None)


def test_distinct_messages_are_never_suppressed() -> None:
    clock = _Clock()
    storm = LogStormFilter(rate_per_sec=200, clock=clock)

    assert all(storm.filter(_record(f"message {index}")) for index in range(100))


def test_repeated_message_is_capped_and_reports_the_dropped_count() -> None:
    clock = _Clock()
    storm = LogStormFilter(rate_per_sec=200, clock=clock)

    emitted = 0
    for _ in range(100):
        record = _record("same failure")
        if storm.filter(record):
            emitted += 1
            assert record.msg == "same failure"
    assert emitted == 10

    clock.now += 1.0
    summary = _record("same failure")
    assert storm.filter(summary)
    assert summary.msg == "[+90 suppressed] same failure"


def test_errors_have_a_larger_budget_than_warnings() -> None:
    clock = _Clock()
    storm = LogStormFilter(rate_per_sec=200, clock=clock)

    warning_hits = sum(storm.filter(_record("boom", level=logging.WARNING)) for _ in range(60))
    error_hits = sum(storm.filter(_record("boom", level=logging.ERROR)) for _ in range(60))

    assert warning_hits == 10
    assert error_hits == 60


def test_tracked_keys_are_bounded() -> None:
    clock = _Clock()
    storm = LogStormFilter(rate_per_sec=200, max_tracked_keys=16, clock=clock)

    for index in range(100):
        storm.filter(_record(f"unique {index}"))

    assert len(storm._per_key) == 16
    assert len(storm._suppressed) == 16


def test_global_rate_caps_total_output() -> None:
    clock = _Clock()
    storm = LogStormFilter(rate_per_sec=10, burst=10, clock=clock)

    emitted = sum(storm.filter(_record(f"line {index}")) for index in range(50))

    assert emitted == 10


def test_zero_rate_disables_the_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYRM_LOG_RATE_LIMIT", "0")
    storm = LogStormFilter(clock=_Clock())

    assert all(storm.filter(_record("spam")) for _ in range(1000))


def test_invalid_rate_setting_falls_back_to_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYRM_LOG_RATE_LIMIT", "not-a-number")
    storm = LogStormFilter(clock=_Clock())

    assert storm._enabled


def test_first_error_survives_an_exhausted_global_bucket() -> None:
    storm = LogStormFilter(rate_per_sec=1, burst=1, clock=_Clock())

    assert storm.filter(_record("warning one"))
    assert not storm.filter(_record("warning two"))
    assert storm.filter(_record("error one", level=logging.ERROR))


def test_summary_prefix_keeps_percent_arguments_intact() -> None:
    clock = _Clock()
    storm = LogStormFilter(clock=clock)

    for _ in range(102):
        storm.filter(_record("failed %s", level=logging.ERROR))
    clock.now += 1.0
    record = _record("failed %s", level=logging.ERROR)
    record.args = ("payload",)

    assert storm.filter(record)
    assert record.getMessage().endswith("failed payload")
    assert record.getMessage().startswith("[+")
