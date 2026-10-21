"""Tests for app.database.operations.sqlite_storage_busy."""

from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest
from sqlalchemy.exc import DBAPIError

from app.database.operations.sqlite_storage_busy import (
    is_sqlite_storage_busy,
    sqlite_busy_retry_after_seconds,
)


class TestIsSqliteStorageBusy:
    def test_raw_sqlite3_locked(self) -> None:
        exc = sqlite3.OperationalError("database is locked")
        assert is_sqlite_storage_busy(exc) is True

    def test_raw_sqlite3_busy(self) -> None:
        exc = sqlite3.OperationalError("database is busy")
        assert is_sqlite_storage_busy(exc) is True

    def test_raw_sqlite3_unrelated(self) -> None:
        exc = sqlite3.OperationalError("disk I/O error")
        assert is_sqlite_storage_busy(exc) is False

    def test_sqlalchemy_wrapping_locked(self) -> None:
        orig = sqlite3.OperationalError("database is locked")
        sa_exc = DBAPIError.instance(
            statement="SELECT 1",
            params=None,
            orig=orig,
            dbapi_base_err=sqlite3.Error,
        )
        assert is_sqlite_storage_busy(sa_exc) is True

    def test_sqlalchemy_wrapping_unrelated(self) -> None:
        orig = sqlite3.OperationalError("no such table: foo")
        sa_exc = DBAPIError.instance(
            statement="SELECT 1",
            params=None,
            orig=orig,
            dbapi_base_err=sqlite3.Error,
        )
        assert is_sqlite_storage_busy(sa_exc) is False

    def test_non_sqlite_exception(self) -> None:
        assert is_sqlite_storage_busy(ValueError("unrelated")) is False

    def test_chained_exception(self) -> None:
        inner = sqlite3.OperationalError("database is locked")
        outer = RuntimeError("wrapper")
        outer.__cause__ = inner
        assert is_sqlite_storage_busy(outer) is True


class TestSqliteBusyRetryAfterSeconds:
    @pytest.mark.parametrize(
        ("timeout_ms", "expected"),
        [
            (0, 1),
            (-100, 1),
            (500, 1),
            (1000, 1),
            (5000, 5),
            (30000, 30),
            (60000, 60),
            (120000, 60),
        ],
    )
    def test_retry_computation(self, timeout_ms: int, expected: int) -> None:
        with patch(
            "app.database.operations.sqlite_storage_busy.get_sqlite_busy_timeout_ms",
            return_value=timeout_ms,
        ):
            assert sqlite_busy_retry_after_seconds() == expected
