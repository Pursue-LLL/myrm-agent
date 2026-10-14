"""Timeout detection helper for the browser toolkit.

Patchright's ``TimeoutError`` is a distinct class that does not subclass the
builtin ``TimeoutError``, so any code that touches patchright must recognize
both. Centralizing that knowledge here prevents call sites from re-discovering
it or writing fragile ``except TimeoutError`` clauses.

[POS]
Single source for unified timeout exception detection across browser toolkit.
"""

from __future__ import annotations

from functools import cache


@cache
def timeout_error_types() -> tuple[type[BaseException], ...]:
    """Return the builtin and patchright timeout classes, for use in ``except`` clauses.

    patchright is imported on first call rather than at module import, so loading the
    toolkit neither pays for the driver nor requires the optional ``[browser]`` extra;
    without it only the builtin class can be raised.
    """
    try:
        from patchright.async_api import TimeoutError as PlaywrightTimeoutError
    except ImportError:
        return (TimeoutError,)
    return (TimeoutError, PlaywrightTimeoutError)


def is_timeout_error(exc: BaseException) -> bool:
    """Return True when ``exc`` is a builtin or patchright timeout."""
    return isinstance(exc, timeout_error_types())
