"""``fenced_block_at`` names the code block a cut would split, reading fences as the router splitter does.

Hand-picked cases pin each rule. A sweep over every cut position of random documents checks the function against a
small CommonMark reader that shares nothing with it.
"""

import random
import re

import pytest

from app.channels.rendering.splitter import fenced_block_at

pytestmark = pytest.mark.timeout(30)

DOC = "intro\n```python\ncode\n```\nafter\n"
OPENER = DOC.index("```python")
CLOSER = DOC.index("```\nafter")
CLOSER_END = CLOSER + 3


@pytest.mark.parametrize("position", [0, 3, OPENER, CLOSER_END, CLOSER_END + 1, len(DOC)])
def test_a_cut_outside_every_block_splits_none(position):
    assert fenced_block_at(DOC, position) is None


@pytest.mark.parametrize(
    "position",
    [OPENER + 1, OPENER + 5, DOC.index("code"), CLOSER, CLOSER + 1, CLOSER_END - 1],
    ids=[
        "after-first-fence-char",
        "in-opening-line",
        "in-code",
        "before-closing-fence",
        "in-closing-fence",
        "last-fence-char",
    ],
)
def test_a_cut_inside_a_block_names_where_it_starts_and_ends(position):
    assert fenced_block_at(DOC, position) == (OPENER, CLOSER_END)


def test_a_block_that_is_never_closed_has_no_end():
    text = "intro\n```\ncode\nmore"
    assert fenced_block_at(text, text.index("code")) == (6, None)
    assert fenced_block_at(text, len(text)) == (6, None)


def test_a_cut_before_the_opening_line_of_an_unclosed_block_splits_none():
    text = "intro\n```\ncode"
    assert fenced_block_at(text, 6) is None
    assert fenced_block_at(text, 3) is None


def test_a_longer_outer_fence_holds_the_fences_inside_it():
    text = "````md\n```py\nx\n```\n```py\ny\n```\n````\ntail"
    outer_end = text.index("````\ntail") + 4
    for needle in ("x", "y", "```py\ny", "```\n```py"):
        assert fenced_block_at(text, text.index(needle)) == (0, outer_end), needle
    assert fenced_block_at(text, outer_end) is None


def test_a_tilde_block_is_a_block():
    text = "intro\n~~~js\ncode\n~~~\nafter"
    assert fenced_block_at(text, text.index("code")) == (6, text.index("~~~\nafter") + 3)


def test_a_fence_of_the_other_character_is_code():
    text = "```\n~~~\nx\n~~~\n```\nafter"
    assert fenced_block_at(text, text.index("x")) == (0, text.index("```\nafter") + 3)
    text = "~~~\n```\nx\n```\n~~~\nafter"
    assert fenced_block_at(text, text.index("x")) == (0, text.index("~~~\nafter") + 3)


def test_a_shorter_fence_is_code_and_a_longer_one_closes():
    text = "````\n```\nx\n`````\nafter"
    closing = text.index("`````")
    assert fenced_block_at(text, text.index("x")) == (0, closing + 5)
    assert fenced_block_at(text, closing + 5) is None


def test_a_fence_with_an_info_string_does_not_close():
    text = "```\n```python\nx\n```\nafter"
    assert fenced_block_at(text, text.index("x")) == (0, text.index("```\nafter") + 3)


def test_triple_backticks_inside_a_line_open_nothing():
    text = "say ```x``` now\nmore ```y```\n"
    assert all(fenced_block_at(text, position) is None for position in range(len(text) + 1))


def test_the_second_block_is_named_not_the_first():
    text = "```\na\n```\ntext\n```\nb\n```"
    second = text.rindex("```\nb")
    assert fenced_block_at(text, text.index("a")) == (0, text.index("```\ntext") + 3)
    assert fenced_block_at(text, text.index("text")) is None
    assert fenced_block_at(text, text.index("b")) == (second, len(text))


def test_an_empty_text_has_no_block():
    assert fenced_block_at("", 0) is None


# --- every cut of random documents, against an independent reader -------------------------------------------------

_FENCE_LINE = re.compile(r"^[ \t]*(`{3,10}|~{3,10})([^`]*)$")
_LINES = (
    "prose",
    "",
    "code line",
    "```",
    "```python",
    "````",
    "`````",
    "~~~",
    "~~~~",
    "~~~js",
    "text ```x``` text",
    "    ```",
)


def _blocks(text: str) -> list[tuple[int, int | None]]:
    """The blocks of ``text`` as (start of the opening line, end of the closing line or None), read the CommonMark way."""
    found: list[tuple[int, int | None]] = []
    start = -1
    opener = ""
    offset = 0
    for line in text.split("\n"):
        end = offset + len(line)
        fence = _FENCE_LINE.match(line)
        if fence and start < 0:
            start, opener = offset, fence.group(1)
        elif fence and not fence.group(2).strip() and fence.group(1)[0] == opener[0] and len(fence.group(1)) >= len(opener):
            found.append((start, end))
            start = -1
        offset = end + 1
    if start >= 0:
        found.append((start, None))
    return found


def _expected(text: str, position: int) -> tuple[int, int | None] | None:
    return next(((start, end) for start, end in _blocks(text) if start < position and (end is None or position < end)), None)


def test_every_cut_of_random_documents_matches_an_independent_reader():
    mismatches: list[tuple[str, int]] = []
    for seed in range(300):
        rng = random.Random(seed)
        text = "\n".join(rng.choice(_LINES) for _ in range(rng.randint(1, 14)))
        mismatches += [
            (text, position) for position in range(len(text) + 3) if fenced_block_at(text, position) != _expected(text, position)
        ]
    assert not mismatches, mismatches[:3]
