"""Retry of SkillStore operations on transient SQLite errors.

[INPUT]
- (none)

[OUTPUT]
- db_retry: Decorator retrying a synchronous store operation on lock contention and other transient database errors.

[POS]
Transient-error retry for SkillStore operations.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Callable
from functools import wraps

logger = logging.getLogger(__name__)

__all__ = ["db_retry"]


def db_retry[**P, R](
    max_retries: int = 5, initial_delay: float = 0.1, backoff: float = 2.0
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Retry on transient SQLite errors with exponential backoff.

    Handles OperationalError (e.g. "database is locked") and DatabaseError.
    Does NOT retry programming errors like InterfaceError.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            delay = initial_delay
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (sqlite3.OperationalError, sqlite3.DatabaseError) as exc:
                    if attempt == max_retries - 1:
                        logger.error(
                            "DB %s failed after %d retries: %s",
                            func.__name__,
                            max_retries,
                            exc,
                        )
                        raise
                    logger.warning(
                        "DB %s retry %d/%d: %s",
                        func.__name__,
                        attempt + 1,
                        max_retries,
                        exc,
                    )
                    time.sleep(delay)
                    delay *= backoff
            raise AssertionError("unreachable: the final attempt re-raises")

        return wrapper

    return decorator
