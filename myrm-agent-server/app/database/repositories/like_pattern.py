"""LIKE patterns that match the text a person typed, character for character.

[INPUT]
- (none)

[OUTPUT]
- LIKE_ESCAPE / LIKE_ESCAPE_CLAUSE: the escape character and the ``ESCAPE`` clause every ``LIKE`` using the pattern carries
- like_contains_pattern(): the ``%...%`` pattern for a typed query, or ``None`` when it has nothing to search for

[POS]
The substring channel of chat search. The trigram index cannot answer a query under three characters and the FTS
expression flattens punctuation (``C++`` becomes ``C``), so the sidebar, the search dialog, the ``@chat:`` picker and the
model's conversation search fall back to ``LIKE``. The fallback reads what was typed, never the FTS expression: ``"`` is the
phrase delimiter of a typed query and is dropped, ``%``, ``_`` and the escape character are literal, and surrounding
whitespace is not part of the search. A query left with nothing is no pattern, because ``%%`` would match every row.
"""

from __future__ import annotations

LIKE_ESCAPE = "\\"
LIKE_ESCAPE_CLAUSE = f"ESCAPE '{LIKE_ESCAPE}'"


def like_contains_pattern(raw_query: str) -> str | None:
    """The pattern for rows that contain ``raw_query``, or ``None`` when nothing searchable is left of it."""
    needle = raw_query.replace('"', "").strip()
    if not needle:
        return None
    escaped = needle.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2).replace("%", f"{LIKE_ESCAPE}%").replace("_", f"{LIKE_ESCAPE}_")
    return f"%{escaped}%"
