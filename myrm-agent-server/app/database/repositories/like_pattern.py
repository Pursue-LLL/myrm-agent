"""The text to look for, and the LIKE pattern for it, when a person typed a chat search.

[INPUT]
- (none)

[OUTPUT]
- LIKE_ESCAPE / LIKE_ESCAPE_CLAUSE: the escape character and the ``ESCAPE`` clause every ``LIKE`` using the pattern carries
- typed_needle(): the text to look for in a typed query, or ``None`` when nothing searchable is left of it
- like_contains_pattern(): the ``%...%`` pattern for that text, or ``None`` when there is none

[POS]
The substring channel of chat search. The trigram index cannot answer a query under three characters and the FTS
expression flattens punctuation (``C++`` becomes ``C``), so the sidebar, the search dialog, the ``@chat:`` picker and the
model's conversation search fall back to ``LIKE``. The fallback reads what was typed, never the FTS expression:
surrounding whitespace is not part of the search and ``%``, ``_`` and the escape character are literal. ``"`` only
delimits a phrase in a typed query, so searches over message text drop it; a caller that searches text where a quote is an
ordinary character (the sidebar over chat titles) keeps it. A query left with nothing is no needle and no pattern,
because ``%%`` would match every row.
"""

from __future__ import annotations

LIKE_ESCAPE = "\\"
LIKE_ESCAPE_CLAUSE = f"ESCAPE '{LIKE_ESCAPE}'"


def typed_needle(raw_query: str, *, keep_quotes: bool = False) -> str | None:
    """What to look for in ``raw_query``, or ``None`` when nothing searchable is left of it."""
    needle = (raw_query if keep_quotes else raw_query.replace('"', "")).strip()
    return needle or None


def like_contains_pattern(raw_query: str, *, keep_quotes: bool = False) -> str | None:
    """The pattern for rows that contain the typed text, or ``None`` when ``typed_needle`` finds nothing to search for."""
    needle = typed_needle(raw_query, keep_quotes=keep_quotes)
    if needle is None:
        return None
    escaped = needle.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2).replace("%", f"{LIKE_ESCAPE}%").replace("_", f"{LIKE_ESCAPE}_")
    return f"%{escaped}%"
