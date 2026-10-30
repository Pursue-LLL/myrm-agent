"""db_retry retries sqlite3 database errors with growing pauses and lets everything else through at once."""

import sqlite3
from collections.abc import Callable

import pytest

from myrm_agent_harness.agent.skills.evolution.db import _store_retry
from myrm_agent_harness.agent.skills.evolution.db._store_retry import db_retry


@pytest.fixture
def pauses(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record the pauses between attempts instead of sleeping."""
    recorded: list[float] = []
    monkeypatch.setattr(_store_retry.time, "sleep", recorded.append)
    return recorded


def _flaky(error: Exception, failures: int) -> tuple[Callable[[], str], list[int]]:
    """An operation raising ``error`` on its first ``failures`` calls, then returning ``"done"``, and the log of its calls."""
    calls: list[int] = []

    def operation() -> str:
        calls.append(len(calls) + 1)
        if len(calls) <= failures:
            raise error
        return "done"

    return operation, calls


def test_a_locked_database_is_retried_until_the_operation_succeeds(pauses: list[float]) -> None:
    operation, calls = _flaky(sqlite3.OperationalError("database is locked"), failures=2)

    assert db_retry()(operation)() == "done"

    assert len(calls) == 3
    assert pauses == [0.1, 0.2]


def test_the_last_failure_is_raised_once_the_attempts_are_used_up(pauses: list[float]) -> None:
    operation, calls = _flaky(sqlite3.OperationalError("database is locked"), failures=99)

    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        db_retry(max_retries=3, initial_delay=0.5, backoff=3.0)(operation)()

    assert len(calls) == 3
    assert pauses == [0.5, 1.5]


def test_the_default_settings_make_five_attempts_and_pause_one_and_a_half_seconds(pauses: list[float]) -> None:
    operation, calls = _flaky(sqlite3.OperationalError("database is locked"), failures=99)

    with pytest.raises(sqlite3.OperationalError):
        db_retry()(operation)()

    assert len(calls) == 5
    assert sum(pauses) == pytest.approx(1.5)


@pytest.mark.parametrize(
    "error",
    [
        sqlite3.IntegrityError("UNIQUE constraint failed"),
        sqlite3.ProgrammingError("bad statement"),
        sqlite3.DataError("too big"),
    ],
    ids=lambda error: type(error).__name__,
)
def test_every_database_error_is_retried_not_only_lock_contention(
    error: sqlite3.DatabaseError, pauses: list[float]
) -> None:
    operation, calls = _flaky(error, failures=99)

    with pytest.raises(type(error)):
        db_retry()(operation)()

    assert len(calls) == 5


@pytest.mark.parametrize(
    "error",
    [
        sqlite3.InterfaceError("connection closed"),
        ValueError("not a database problem"),
        RuntimeError("store is closed"),
    ],
    ids=lambda error: type(error).__name__,
)
def test_other_errors_propagate_on_the_first_attempt(error: Exception, pauses: list[float]) -> None:
    operation, calls = _flaky(error, failures=99)

    with pytest.raises(type(error)):
        db_retry()(operation)()

    assert len(calls) == 1
    assert pauses == []
