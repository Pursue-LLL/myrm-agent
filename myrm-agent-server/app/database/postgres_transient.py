"""Detect PostgreSQL transient / retry-friendly errors (SQLSTATE and optional asyncpg types)."""

from __future__ import annotations

from collections.abc import Iterator

# Retry-oriented SQLSTATE values (PostgreSQL / asyncpg; see PostgreSQL docs).
_RETRYABLE_PG_SQLSTATES: frozenset[str] = frozenset(
    {
        "40001",  # serialization_failure
        "40P01",  # deadlock_detected
        "40003",  # statement_completion_unknown
        "08006",  # connection_failure
        "08003",  # connection_does_not_exist
        "53300",  # too_many_connections
    }
)


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


def _walk_orig_chain(exc: BaseException | None) -> Iterator[BaseException]:
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        yield cur
        seen.add(id(cur))
        cur = getattr(cur, "__cause__", None)


def _sqlstate_retryable(obj: BaseException | None) -> bool:
    if obj is None:
        return False
    st = getattr(obj, "sqlstate", None)
    if isinstance(st, str) and st in _RETRYABLE_PG_SQLSTATES:
        return True
    try:
        import asyncpg.exceptions as apg
    except ImportError:
        return False
    # SQLSTATE 40001 covers serialization_failure; explicit types cover drivers that omit sqlstate.
    return isinstance(
        obj,
        (
            apg.DeadlockDetectedError,
            apg.CannotConnectNowError,
            apg.ConnectionDoesNotExistError,
            apg.TooManyConnectionsError,
        ),
    )


def is_postgres_transient_operational(exc: BaseException) -> bool:
    """True when the exception chain matches ``_RETRYABLE_PG_SQLSTATES`` or listed asyncpg types."""
    for node in _walk_exception_chain(exc):
        if _sqlstate_retryable(node):
            return True
        orig = getattr(node, "orig", None)
        for sub in _walk_orig_chain(orig if isinstance(orig, BaseException) else None):
            if _sqlstate_retryable(sub):
                return True
    return False


def postgres_transient_retry_after_seconds() -> int:
    """HTTP ``Retry-After`` (seconds) for PostgreSQL transient responses; env ``POSTGRES_TRANSIENT_RETRY_AFTER_SECONDS``."""
    from app.config.settings import settings

    return settings.database.postgres_transient_retry_after_seconds


__all__ = [
    "is_postgres_transient_operational",
    "postgres_transient_retry_after_seconds",
]
