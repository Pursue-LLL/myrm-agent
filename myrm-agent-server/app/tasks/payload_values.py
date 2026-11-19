"""Typed reads of the loosely typed values in a task payload snapshot.

[OUTPUT]
- optional_str(): a non-blank string, stripped, else ``None``
- str_list(): the non-blank strings of a list, stripped; ``[]`` for anything that is not a list
- optional_int(): an ``int`` (not a ``bool``), else ``None``
- optional_bool(): a ``bool``, else ``None``

[POS]
The payload is JSON written at enqueue time and read back by the worker, so every field arrives as ``object``; the
resolvers and executors read it through here instead of each keeping private coercion helpers.
"""

from __future__ import annotations


def optional_str(value: object | None) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def str_list(value: object | None) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def optional_int(value: object | None) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def optional_bool(value: object | None) -> bool | None:
    if isinstance(value, bool):
        return value
    return None
