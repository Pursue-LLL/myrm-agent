"""Pattern builders and shared pattern parts of the built-in risk rules.

[INPUT]
- myrm_agent_harness.core.security.detection.leak_detector::DISTINCTIVE_KEY_PATTERNS (POS: The vendor-prefix shapes that identify a key on their own; the gate reads them instead of keeping a list of its own.)

[OUTPUT]
- detector_pattern / keyword_pattern: a privacy detector or a keyword list as a rule pattern
- KEY_START / ASSIGNMENT_OPERATOR / ASSIGNED_VALUE: the parts every ``key = value`` rule is built from; the rule's pattern
  names the ``key`` group, these name where it may start and what ``value`` is
- API_KEY_PATTERN: vendor-prefixed credentials

[POS]
A rule that matches an assignment (``password = ...``, ``Authorization: Bearer ...``) captures its ``key`` and ``value``
groups; ``match_checks`` then hits only when the value is a secret and not a reference to one.
"""

from __future__ import annotations

import re

from myrm_agent_harness.core.security.detection.leak_detector import DISTINCTIVE_KEY_PATTERNS

# A key starts after anything but a letter or digit, so ``_`` and ``-`` are allowed before it: ``DB_PASSWORD``,
# ``GROQ_API_KEY`` and ``aws_secret_access_key`` hold the key ``password``, ``api_key`` and ``secret_access_key``, which
# ``\b`` would not find (an underscore is a word character). It is one lookbehind, so the cost does not grow with the
# length of the prefix.
KEY_START = r"(?<![A-Za-z0-9])"

# ``key = value``, ``key: value`` and a quoted ``"key": "value"`` all give the assignment's value in the ``value`` group.
ASSIGNMENT_OPERATOR = r"""["']?\s*[:=]\s*["']?"""
ASSIGNED_VALUE = r"""(?P<value>[^\s"']+)"""

# Vendor-prefixed credentials, matched case-sensitively and only at the start of a token, so a word that merely ends in
# a prefix (``task-``, ``disk-``) or a long slug is not a key. ``sk-`` is the gate's own and covers the keys of
# OpenAI-compatible relays, which the table's ``sk-`` shapes (48 and 32 characters) do not; the rest is the harness's
# table of shapes a prefix identifies on its own.
API_KEY_PATTERN = (
    r"(?<![A-Za-z0-9])(?:sk-[A-Za-z0-9_-]{20,}" + "".join(f"|{pattern.pattern}" for _, pattern in DISTINCTIVE_KEY_PATTERNS) + ")"
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
