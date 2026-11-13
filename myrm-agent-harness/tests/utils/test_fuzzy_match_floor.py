"""Confidence floor of the fuzzy chain: an edit must not rewrite lines its caller never named.

``block_anchored`` and ``context_aware`` anchor on the first and last line and let the lines in between differ, so a
replacement built from a misremembered block overwrites real lines with the caller's guess. The floor
``CONTENT_PRESERVING_MIN_CONFIDENCE`` keeps only the strategies whose match is the fragment's own text.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.utils._fuzzy_strategies import STRATEGIES
from myrm_agent_harness.utils.fuzzy_match import (
    CONTENT_PRESERVING_MIN_CONFIDENCE,
    fuzzy_find,
    fuzzy_replace,
)

_FILE = "\n".join(
    [
        "import os",
        "",
        "def load(path):",
        "    with open(path) as fh:",
        "        raw = fh.read()",
        "    data = json.loads(raw)",
        "    validate(data)",
        "    return data",
        "",
        "def save(path, data):",
        "    pass",
    ]
)

# First and last line are the file's; two of the four lines in between are misremembered (block_anchored).
_MISREMEMBERED_BLOCK = "\n".join(
    [
        "def load(path):",
        "    with open(path, encoding='utf-8') as fh:",
        "        text = fh.read()",
        "    data = json.loads(text)",
        "    validate(data)",
        "    return data",
    ]
)

_HALF_FILE = "def f(x):\n    a = 1\n    b = 2\n    c = 3\n    d = 4\n    return a\n"
# Same line count, half of the lines in between are the file's, the others are unrelated (context_aware).
_HALF_BLOCK = "def f(x):\n    a = 1\n    b = 2\n    qqqqqqqqqqqqqqqqqqqq()\n    wwwwwwwwwwwwwwwwwwww()\n    return a"


def test_without_a_floor_a_misremembered_block_still_matches() -> None:
    match = fuzzy_find(_FILE, _MISREMEMBERED_BLOCK)
    assert match is not None
    assert match.strategy == "block_anchored"


def test_without_a_floor_a_half_remembered_block_still_matches() -> None:
    match = fuzzy_find(_HALF_FILE, _HALF_BLOCK)
    assert match is not None
    assert match.strategy == "context_aware"


def test_the_floor_refuses_a_misremembered_block() -> None:
    assert fuzzy_find(_FILE, _MISREMEMBERED_BLOCK, min_confidence=CONTENT_PRESERVING_MIN_CONFIDENCE) is None


def test_the_floor_refuses_a_half_remembered_block() -> None:
    assert fuzzy_find(_HALF_FILE, _HALF_BLOCK, min_confidence=CONTENT_PRESERVING_MIN_CONFIDENCE) is None


def test_a_refused_replace_leaves_the_content_untouched() -> None:
    result = fuzzy_replace(
        _FILE,
        _MISREMEMBERED_BLOCK,
        _MISREMEMBERED_BLOCK.replace("return data", "return data or {}"),
        min_confidence=CONTENT_PRESERVING_MIN_CONFIDENCE,
    )
    assert result.success is False
    assert result.strategy == "none"
    assert result.content == _FILE


def test_without_a_floor_replace_rewrites_the_guessed_lines() -> None:
    result = fuzzy_replace(_FILE, _MISREMEMBERED_BLOCK, _MISREMEMBERED_BLOCK.replace("return data", "return {}"))
    assert result.success is True
    assert "text = fh.read()" in result.content
    assert "raw = fh.read()" not in result.content


@pytest.mark.parametrize(
    ("content", "fragment"),
    [
        pytest.param("a = 1\nb = 2", "b = 2", id="exact"),
        pytest.param("    x = 1\n    y = 2", "x = 1\ny = 2", id="indentation-stripped"),
        pytest.param("x  =   1\ny\t=\t2", "x = 1\ny = 2", id="inner-whitespace"),
        pytest.param("if a:\n        b = 1\n        c = 2", "    b = 1\n    c = 2", id="shifted-indentation"),
        pytest.param("line1\nline2", "line1\\nline2", id="escaped-newline"),
        pytest.param("def f():\n    return 1\n", "   def f():\n    return 1   ", id="padded-first-and-last-line"),
    ],
)
def test_the_floor_keeps_variants_that_differ_only_in_whitespace_or_escapes(content: str, fragment: str) -> None:
    match = fuzzy_find(content, fragment, min_confidence=CONTENT_PRESERVING_MIN_CONFIDENCE)
    assert match is not None
    assert match.confidence >= CONTENT_PRESERVING_MIN_CONFIDENCE


def test_the_floor_admits_exactly_the_strategies_that_keep_the_fragments_own_text() -> None:
    """A strategy added to the chain has to be classified on purpose: this set is the decision."""
    admitted = {name for name, _finder, confidence in STRATEGIES if confidence >= CONTENT_PRESERVING_MIN_CONFIDENCE}
    assert admitted == {
        "exact",
        "line_trimmed",
        "whitespace_normalized",
        "indent_flexible",
        "escape_normalized",
        "trimmed_boundary",
    }
