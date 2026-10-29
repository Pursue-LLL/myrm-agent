"""Redaction of the strings inside a nested value.

The walk is bounded in depth, which keeps it independent of the interpreter stack, and it cuts a container where it
holds itself, so a loop costs one visit per container. A container reached by two branches is not a loop and is
redacted in both.

[INPUT]
- (none — pure walker; the caller supplies the text redactor)

[OUTPUT]
- ``redact_nested`` - a copy of a dict/list/tuple tree whose strings (and, on request, dict keys) went through ``leaf(field name, text)``
- ``MAX_DEPTH`` / ``TOO_DEEP`` / ``CIRCULAR`` - the depth limit and the markers that replace a container past it or one that holds itself

[POS]
Shared walker of the redaction domain; ``engine.py`` (approval display), ``agent/event_log`` (event payloads and
dataset export) and the server's chat export bring their own leaf.
"""

from __future__ import annotations

from collections.abc import Callable

# Payloads that are shown or persisted nest a handful of levels; a deeper container is replaced, not walked.
MAX_DEPTH = 32
TOO_DEEP = "[nesting too deep]"
CIRCULAR = "[circular reference]"

# Redacts ``text``, which sits in the field ``key`` ("" when the field has no string name).
type TextRedactor = Callable[[str, str], str]


def redact_nested(value: object, leaf: TextRedactor, *, mask_keys: bool = False) -> object:
    """Return a copy of ``value`` with every string redacted by ``leaf``.

    A string inside a list or tuple is redacted under the name of the field that holds the list. With ``mask_keys`` a
    dict key is redacted too (a map keyed by credential); the value under it still sees the original field name.
    Values that are not strings or containers are returned as they are.
    """
    return _walk(value, "", 1, set(), leaf, mask_keys)


def _walk(value: object, key: str, depth: int, ancestors: set[int], leaf: TextRedactor, mask_keys: bool) -> object:
    """Redact ``value``; ``ancestors`` holds the containers on the path from the root to it."""
    if isinstance(value, str):
        return leaf(key, value)
    if not isinstance(value, dict | list | tuple):
        return value
    if depth > MAX_DEPTH:
        return TOO_DEEP
    if id(value) in ancestors:
        return CIRCULAR
    ancestors.add(id(value))
    if isinstance(value, dict):
        redacted: object = {
            (leaf("", name) if mask_keys and isinstance(name, str) else name): _walk(
                item, name if isinstance(name, str) else "", depth + 1, ancestors, leaf, mask_keys
            )
            for name, item in value.items()
        }
    else:
        items = [_walk(item, key, depth + 1, ancestors, leaf, mask_keys) for item in value]
        redacted = items if isinstance(value, list) else tuple(items)
    ancestors.discard(id(value))
    return redacted
