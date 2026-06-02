"""Detect SQLite lock/busy errors from SQLAlchemy (and optional raw sqlite3) exceptions."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

from sqlalchemy.exc import DBAPIError

from app.database.factory import get_sqlite_busy_timeout_ms


def _walk_exception_chain(exc: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        yield cur
        seen.add(id(cur))
        nxt = cur.__cause__
        if nxt is None:
            nxt = cur.__context__
        cur = nxt


def _orig_chain(exc: BaseException | None) -> Iterator[BaseException]:
    cur: BaseException | None = exc
    seen: set[int] = set()
    while cur is not None and id(cur) not in seen:
        yield cur
        seen.add(id(cur))
        cur = getattr(cur, "__cause__", None)


def _is_sqlite_busy_message(message: str) -> bool:
    m = message.lower()
    return "locked" in m or "busy" in m


def _sqlite_busy_from_sqlite_operational(obj: BaseException | None) -> bool:
    if not isinstance(obj, sqlite3.OperationalError):
        return False
    for part in _orig_chain(obj):
        if isinstance(part, sqlite3.OperationalError) and _is_sqlite_busy_message(str(part)):
            return True
    return False


def is_sqlite_storage_busy(exc: BaseException) -> bool:
    """True when the exception chain indicates SQLite database or table busy/locked (message heuristic)."""
    if isinstance(exc, sqlite3.OperationalError):
        return _is_sqlite_busy_message(str(exc))

    for node in _walk_exception_chain(exc):
        if isinstance(node, DBAPIError):
            if _sqlite_busy_from_sqlite_operational(node.orig):
                return True
        if _sqlite_busy_from_sqlite_operational(node):
            return True

    return False


def sqlite_busy_retry_after_seconds() -> int:
    """Whole seconds for HTTP Retry-After from ``get_sqlite_busy_timeout_ms()``."""
    ms = get_sqlite_busy_timeout_ms()
    if ms <= 0:
        return 1
    sec = max(1, ms // 1000)
    return min(60, sec)


__all__ = [
    "is_sqlite_storage_busy",
    "sqlite_busy_retry_after_seconds",
]
