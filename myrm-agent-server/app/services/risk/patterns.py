"""Pattern builders and shared pattern parts of the built-in risk rules.

[INPUT]
- (none: pure ``re`` helpers)

[OUTPUT]
- detector_pattern / keyword_pattern: a privacy detector or a keyword list as a rule pattern
- ASSIGNMENT_OPERATOR / ASSIGNED_VALUE: the parts every ``key = value`` rule is built from; the rule's pattern names the
  ``key`` group, these name ``value``
- API_KEY_PATTERN: vendor-prefixed credentials

[POS]
A rule that matches an assignment (``password = ...``, ``Authorization: Bearer ...``) captures its ``key`` and ``value``
groups; ``match_checks`` then hits only when the value is a secret and not a reference to one.
"""

from __future__ import annotations

import re

# ``key = value``, ``key: value`` and a quoted ``"key": "value"`` all give the assignment's value in the ``value`` group.
ASSIGNMENT_OPERATOR = r"""["']?\s*[:=]\s*["']?"""
ASSIGNED_VALUE = r"""(?P<value>[^\s"']+)"""

# Vendor-prefixed credentials, matched case-sensitively and only at the start of a token, so a word that merely ends in
# a prefix (``task-``, ``disk-``) or a long slug is not a key. ``sk-`` also covers the keys of OpenAI-compatible relays.
API_KEY_PATTERN = (
    r"(?<![A-Za-z0-9])(?:"
    r"sk-[A-Za-z0-9_-]{20,}"
    r"|[sr]k_(?:live|test)_[A-Za-z0-9]{24,}"
    r"|(?:AKIA|ASIA)[0-9A-Z]{16}"
    r"|gh[pousr]_[A-Za-z0-9]{36,}"
    r"|github_pat_[A-Za-z0-9_]{22,}"
    r"|glpat-[A-Za-z0-9_-]{20,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|AIza[A-Za-z0-9_-]{35}"
    r")"
)


def detector_pattern(detector: re.Pattern[str]) -> str:
    """The source of a privacy detector as a rule pattern; rules are compiled without flags, so its case-insensitivity
    is written into the pattern."""
    return f"(?i){detector.pattern}" if detector.flags & re.IGNORECASE else detector.pattern


def keyword_pattern(*terms: str) -> str:
    """A case-insensitive pattern that matches any of *terms*.

    A Latin term matches only as a word, with an optional plural: ``tin`` is not in ``meeting`` and ``vat`` is not in
    ``private``. A term with other characters matches anywhere, because Chinese is written without word spaces.
    """
    alternatives = [
        rf"(?<![A-Za-z0-9]){re.escape(term)}(?:e?s)?(?![A-Za-z0-9])" if term.isascii() else re.escape(term) for term in terms
    ]
    return "(?i)(?:" + "|".join(alternatives) + ")"
